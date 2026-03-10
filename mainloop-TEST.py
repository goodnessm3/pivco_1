from pin_assignments import *
from machine import Pin, I2C
import time

"""
TUNE_LATCH_PIN = Pin(P_TUNE_LATCH_PIN,Pin.OUT,value=1)
while 1:
    time.sleep(0.01)
    TUNE_LATCH_PIN.low()
    time.sleep(0.01)
    TUNE_LATCH_PIN.high()
"""

"""
TEST_CS_PIN = Pin(P_AEN_PIN,Pin.OUT,value=0)
#TEST_CS_PIN = Pin(P_TEST_CS_PIN,Pin.OUT,value=1)  # TODO - use actual CS when PCB is connected
TUNE_LATCH_PIN = Pin(P_TUNE_LATCH_PIN,Pin.OUT,value=1)

# for other testing just always connect the tune bus first thing
time.sleep(0.01)
#TEST_CS_PIN.low()  # logical high +12 V on CS
TEST_CS_PIN.high()
#time.sleep(0.01)
TUNE_LATCH_PIN.low()  # rising edge of clock pin
time.sleep(0.01)
TUNE_LATCH_PIN.high()  # falling edge of clock, data is latched
#time.sleep(0.01)
#TEST_CS_PIN.high()  # data goes low but we saved the bit
TEST_CS_PIN.low()

del TEST_CS_PIN
"""


from array import array
from readmidi import MidiReader
import math
from freq_count_nodma import freq_counter_cleanup, freq_count_reset
from mydacs import send_dac_value, dac_setup, ADDRESS_MANAGER, prepare_tune_latch

prepare_tune_latch()  # just latch something to start off with
time.sleep(0.1)  # make sure the latch state machine is ready to recieve the rising edge of AEN
dac_setup()  # manages reset pin

from oscillator import Oscillator
from lcd1602 import LCD
import ADSR2, LFO2
from controls import Controls, DisplayManager
import settings_manager
from filtertable import FILTER_CVS  # for tracking cutoff freq with volts/octave

i2c = I2C(1, scl=Pin(P_I2C_SCL), sda=Pin(P_I2C_SDA))  # for driving the LCD
# I2C block 1 is associated with pins 26 and 27 (defined in pin assignments file)
DISPLAY = LCD(i2c)  # set up the text display

# TODO: specify DAC output order in one place
# this is the order of signals as they come out of the DAC chip
# external mix cv, suboctave, VCA, PWM, coarse osc, fine osc, filter c/o, filter res
#        0            1        2    3     4            5         6            7


class Voice:
    
    def __init__(self, mods, retune=True, cutoff_freq_tracking=True):
        
        # setting static values but in future these will be args

        self.identity = 0  # HARDCODED for now, but this is the "caller" argument for mod sources

        # !! HACK ALERT - PWM INDEX IS HARDCODED HERE !! #
        if retune:
            send_dac_value(3, 127)
            # regardless of what it was set to before, need ca. 50% duty cycle to get good measurements

        self.osc = Oscillator(4, 5)  # we are manually specifying coarse and fine DAC index here
        # eventually need to give voice an address as well for polyphonic

        # hacky way to specify values during empirical PID tuning
        # 512, 128, 128 seem good!!
        # not any more when changing to EMA.......
        self.osc.pid.p = 128
        self.osc.pid.i = 64
        self.osc.pid.d = 512
        
        self.osc.setup(retune=retune)

        self.monitoring = False  # set to true when this voice is connected to the tune bus for monitoring. Then we can
        # get corrections from the oscillator PID to autotune the frequency and apply it with the rest of the
        # modulations

        # indices of the DAC channels that control these parameters
        self.xfade_idx = 0  # actually external mix now TODO
        self.suboctave_idx = 1
        self.pwm_idx = 3
        self.envelope_idx = 2
        self.resonance_idx = 7
        self.cutoff_idx = 6
        
        # these values are pushed into the voice class from the main loop update function
        # all are always values from 0 to 255 to match the DAC's expected input values
        self.coarse = 0
        self.fine = 0
        self.xfade = 0
        self.suboctave = 0
        self.pwm = 0
        self.envelope = 0
        self.resonance = 0
        self.cutoff = 0

        self.filter_track = 0  # signal added to the filter output to track with volts/octave

        # we need to put these in a list so we can access the variables for applying modulation sources:
        #self.variable_names = ["coarse", "fine", "xfade", "suboctave", "pwm", "envelope", "resonance", "cutoff"]
        self.variable_names = ["xfade","suboctave", "envelope", "pwm", "coarse", "fine", "cutoff", "resonance"]
        # we are storing names because we use getattr. Would probably be better to just do by list index
        # TODO: by list index instead
        
        self.last_sent = [0,0,0,0,0,0,0,0]  # don't update a DAC if the value hasn't changed. Use this
        # to keep track of the last value we sent to the DAC for a given channel

        # current statuses
        self.note_down = False
        self.cutoff_freq_tracking = cutoff_freq_tracking  # TODO: configurable later
        
        self.modulation_assignments = mods  # a list where the index is the DAC channel and the list entry is
        # a list of objects we should query via their get() method to get a modulation amount
        # so [[], [LFO1]] means nothing is applied to channel 0 and LFO1 is applied to channel 1

        self.adsrs = []
        # build a list of ADSR objects that modulate this voice. We need this in order to send gate signals
        # when the note is turned on/off
        for ls in self.modulation_assignments:
            for entity in ls:
                if type(entity) == ADSR2.ADSR:
                    self.adsrs.append(entity)
                    
    
    def send(self, note_down, midinote=None):
        
        # receive an instruction from the main loop to play a note
        # expects a midi note index

        if self.monitoring:
            freq_count_reset()  # throw out old freq measurements otherwise the new note correction signal
            # will be based on the old frequency

        if note_down and not self.note_down:
            self.note_down = True

            if midinote:
                self.coarse, self.fine = self.osc.play_note(midinote)
                if self.cutoff_freq_tracking:
                    self.filter_track = FILTER_CVS[midinote]
                for envelope in self.adsrs:
                    envelope.gate(self.identity, True)  # envelopes will start attacking

        elif not note_down and self.note_down:
            self.note_down = False
            for envelope in self.adsrs:
                envelope.gate(self.identity, False)  # tell envelopes to release
            # we can grab this voice for another purpose if needed in which case the envelopes are remembering
            # their own states and won't "glitch" if restarted


    def update(self):

        # TODO: don't bother get'ing from a mod source that isn't in use
        coarse_correction = fine_corrected = 0
        if self.monitoring:
            pass
            #coarse_correction, fine_corrected = self.osc.correct()  # TODO - correction function changed
            #print("freq corrections coarse and fine were: ", coarse_correction, fine_corrected)

        for idx, ls in enumerate(self.modulation_assignments):
            modulation_sum = 0  # TODO: what if we want to multiply modulations, not add?
            for entity in ls:
                #print(entity)
                #print(entity.get(self.identity))
                modulation_sum += entity.get(self.identity) >> 8  # mod sources are higher-res
                # TODO - just decide on a resolution and stick to it!! Voices should be 16-bit too

            base_variable = self.variable_names[idx]  # so we can refer by name

            # overwrite coarse and fine if they need correction
            if base_variable == "coarse" and coarse_correction != 0:
                self.coarse += coarse_correction
            elif base_variable == "fine" and fine_corrected != 0:
                self.fine = fine_corrected

            #print(f"for {base_variable}, modsum = {modulation_sum}")

            modulation_sum += getattr(self, base_variable)   # add the base value around which we modulate

            #print("now ", modulation_sum)

            if base_variable == "cutoff":
                modulation_sum = 255 - modulation_sum  # HACK ALERT! The filter is BACKWARDS LOL
                # in the circuit higher CV -> lower cutoff, so this inversion makes it so high CV -> more open

            if self.last_sent[idx] == modulation_sum:
                pass  # don't bother sending a DAC signal at all if nothing changed
            else:
                #print("sending", modulation_sum, "to", idx)
                send_dac_value(idx, modulation_sum)
                self.last_sent[idx] = modulation_sum


    def export(self):

        out = []
        for v in self.variable_names:
            out.append(getattr(self, v))

        return out

    def load(self, ls):

        for i in range(len(ls)):
            varname = self.variable_names[i]
            setattr(self, varname, ls[i])





# setting up tuning line


#TEST_CS_PIN = AEN_PIN  # !!!!!! 11:57 03/08
#TEST_CS_PIN = Pin(P_TEST_CS_PIN,Pin.OUT,value=1)  # TODO - use actual CS when PCB is connected
#TUNE_LATCH_PIN = Pin(P_TUNE_LATCH_PIN,Pin.OUT,value=1)
"""
# for other testing just always connect the tune bus first thing
time.sleep(0.01)
#TEST_CS_PIN.low()  # logical high +12 V on CS
TEST_CS_PIN.high()
time.sleep(0.01)
TUNE_LATCH_PIN.low()  # rising edge of clock pin
time.sleep(0.01)
TUNE_LATCH_PIN.high()  # falling edge of clock, data is latched
time.sleep(0.01)
#TEST_CS_PIN.high()  # data goes low but we saved the bit
TEST_CS_PIN.low()     
"""
# build all voices and modulation sources
ADSRLIST = [ADSR2.ADSR(), ADSR2.ADSR(),ADSR2.ADSR(),ADSR2.ADSR(),ADSR2.ADSR(),ADSR2.ADSR(),ADSR2.ADSR(),ADSR2.ADSR()]
LFOLIST = [LFO2.LFO(), LFO2.LFO(), LFO2.LFO(), LFO2.LFO(), LFO2.LFO(), LFO2.LFO(), LFO2.LFO(), LFO2.LFO()]

# TODO - numbers are all messed up since changing to PCB DAC order
# TODO - rather than LFO and ADSR select, do parameter select, each parameter having its own LFO and ADSR
# TODO - if the depth of a mod source is set to 0 then it is considered to be turned off.
tempmodlist = [
                [LFOLIST[6],ADSRLIST[6]],
               [LFOLIST[7],ADSRLIST[7]],
               [LFOLIST[5],ADSRLIST[5]],
               [LFOLIST[1],ADSRLIST[1]],
               [LFOLIST[4],ADSRLIST[4]],
               [LFOLIST[0],ADSRLIST[0]],
               [LFOLIST[3],ADSRLIST[3]],
               [LFOLIST[2],ADSRLIST[2]]
               ]

V = Voice(tempmodlist, retune=True)
V.monitoring = False  # TODO: handle monitoring of multiple voices
VOICES = [V]  # in the future, there be more

MR = MidiReader()
CONTROLS = Controls(VOICES, LFOLIST, ADSRLIST)
DM = DisplayManager(VOICES, LFOLIST, ADSRLIST)

print("Loading saved settings...")
settings_manager.load_object_settings(VOICES, ADSRLIST, LFOLIST)
print("Done")

down_notes = {}  # keep track of which voice is playing which note
 # so we can send key-up signals to them
 # todo - this should be an array


loopcount = 0
loopstart = time.ticks_ms()

# 96 is the highest MIDI note on the keyboard

try:
    while 1:
        ADDRESS_MANAGER.put(0)  # TODO: eventually this will handle addresses 0-7
        loopcount += 1
        DISPLAY.draw_screen()
        MR.read()  # induce the MidiReader to compile messages to read out         
        notes_queue = MR.get_messages("notes")
        controls_queue = MR.get_messages("controls")

        if len(notes_queue) > 1:
            #pass
            #print(notes_queue)
            pass

        if controls_queue:
            for msg in controls_queue:
                CONTROLS.process_control_signal(*msg)
                ret = CONTROLS.get_updated()  # todo - careful we aren't discarding things
                if not ret:
                    continue  # should this be break?
                ob, parm, value = ret[0]
                if parm:  # write the named variable of the specified object
                    # ob.__setattr__(parm, value)  # not this!!
                    setattr(ob, parm, value)  # but this!!
                pair = DM.update(ret[0])  # get a new frame buffer for the LCD
                DISPLAY.update(pair)  # send the new frame buffer for display next loop
        
        for status, note in notes_queue:  # tuples of freq, true/false
            if status:  # True, want to play a new note
                for v in VOICES:  # find the first available voice
                    v.send(False)  # terminate current note
                    down_notes = {}  # can't decay when only 1 voice
                    # this is TESTING code for single voice case and played note prio.
                    v.send(True, note)



                    #!!!!!!!!!!!!!!!!!!!!!!!
                    #v.monitoring = True  # TODO - track which notes are monitored
                    #!!!!!!!!!!!!!!!!!!!!!!!



                    #print(f"Assigned note {note} to {v}")
                    down_notes[note] = v  # keep a reference so we can unplay note
                    break  # we only need to assign to a single voice
            else:  # False, meaning note up
                voice = down_notes.get(note, None)
                # there might be a note up signal for an uplayed note
                # if we ran out of voices to allocate, so just skip it.
                if voice:
                    voice.send(False)  # free up voice
                    #print(f"freeing voice {voice}")
                    
        for q in VOICES:
            q.update()
            


finally:
    print("count", loopcount)
    total_time = time.ticks_diff(time.ticks_ms(), loopstart)

    lps = loopcount / total_time * 1000
    print(f"Averaged {lps} loops per second over {total_time} ms.")
    
    settings_manager.save_object_settings(VOICES, ADSRLIST, LFOLIST)
    freq_counter_cleanup()
    send_dac_value(5, 0)  # manually turn off single voice's VCA
    for q in VOICES:
        q.osc.save_arrays()
        
    


        
