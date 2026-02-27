from machine import Pin, I2C
import time
from array import array

import envelopes
from readmidi import MidiReader
import math
from freq_count_nodma import freq_counter_cleanup

from mydacs import send_dac_value, dac_setup, send_dac_fraction
dac_setup()  # manages reset pin

from oscillator import Oscillator


from lcd1602 import LCD
from LFO import LFO

from variables import PhysicalControlsDict, write_params, PARAMS, LookUp  # manages menu navigation

i2c = I2C(0, scl=Pin(17), sda=Pin(16))  # for driving the LCD display
DISPLAY = LCD(i2c)  # set up the text display
LU = LookUp()  # object that will let us look up parameters set by sliders like cutoff, resonance etc
print(LU)
print(LU.RESONANCE)


DAC_MAP = [None,
           None,
           "XFADE",
           "SUBOCT",
           "PWM",
           "VCA",
           "RESONANCE",
           "CUTOFF"]
# the index in this array tells us which DAC channel to change for this property

def freq2cutoff(freq):
    
    # what voltage do we need for a cutoff of this freq in Hz? Used experimentally determined values
    # made a linear fit of log2(cutoff) vs. PROPORTION of control voltage input
    # that is, the return value from this function is a FRACTION (0 to 1.0) of the 5 V control voltage.
    # 5 V CV range covers 18 kHz down to about 100 Hz (hard to measure at very low freq as full resonance stops working)

    return (math.log2(freq) - 14.2) / -9.45
    # todo: get away from log and use something faster or pre-computed table


class Voice:
    
    def __init__(self):
        
        # setting static values but in future these will be args

        self.osc = Oscillator(0, 1)  # we are manually specifying coarse and fine DAC index here
        # eventually need to give voice an address as well for polyphonic
        self.osc.setup(retune=True)

        # indices of the DAC channels that control these parameters
        self.xfade_idx = 2
        self.suboctave_idx = 3
        self.pwm_idx = 4
        self.envelope_idx = 5
        self.resonance_idx = 6
        self.cutoff_idx = 7
        
        # a local copy of the value from the LU dictionary. We will modify
        # these values in the update function by applying LFOs, envelopes, etc
        self.xfade = 0
        self.suboctave = 0
        self.pwm = 0
        self.envelope = 0
        self.resonance = 0
        self.cutoff = 0
        
        self.last_sent = {}  # don't update a DAC if the value hasn't changed. Use this
        # to keep track of the last value we sent to the DAC for a given channel
        
        

        
        #send_dac_value(self.xfade_idx, LU.XFADE)
        #send_dac_value(self.suboctave_idx, LU.SUBOCT)
        #send_dac_value(self.resonance_idx, LU.RESONANCE)

        
        # current statuses
        self.note_down = False
        self.start_time = time.ticks_ms()  # TODO: shouldn't need this
        # we shouldn't be updating totally idle voices
        
        self.cutoff_freq_tracking = True  # TODO: configurable later
        
        self.envelope_assignments = [
                                    (self.envelope_idx, BASIC, 1.0 ),
                                     (self.cutoff_idx, SLOW, 0.55),
                                     (self.resonance_idx, SLOW, 0.2),
                                     #(self.xfade_idx, BASIC, 1.0),
                                    #(self.pwm_idx, SLOW2, 0.5),
                                    ]
        # which properties are modulated by the envelope?
        # and to what extent? Tuples of (DAC channel, env, scaling factor)
                    
    
    def send(self, note_down, midinote=None):
        
        # recieve an instruction from the main loop to play a note
        # expects a midi note index
        
        #print(f"voice {self} was asked to play {freq} Hz")
        self.start_time = time.ticks_ms()
        # record when the event started so we can update envelope over time

        if midinote:
            freq = NOTES[midinote]  # for filter, tidy this up
        else:
            freq = 20_000  # tidy up but for now arbitrarily open filter
        
        if note_down and not self.note_down:
            self.note_down = True
            if midinote:
                self.osc.play_note(midinote)

        elif not note_down and self.note_down:
            self.note_down = False
            # don't turn anything off, note needs to decay
            # but we can grab this voice for another purpose if needed


    def update(self):
        
        #print(f"Updating voice {self}")
        # running, neither start nor stop
        timedelta = time.ticks_diff(time.ticks_ms(), self.start_time)  # deals with wrapping
        # how many ms has passed since the start of the event?
        # result is an integer number of ms - use to look up modulations.
        
        #print(f"timedelta for update: {timedelta}")
        
        for dac, env, proportion in self.envelope_assignments:  # always need to update something under an envelope
            signal = env.get_level(timedelta, self.note_down)
            if dac == self.cutoff_idx:
                send_dac_fraction(dac, (signal * proportion) + LU.CUTOFF/255.0)

            elif dac == self.resonance_idx:
                send_dac_fraction(dac, signal * proportion + LU.RESONANCE/255.0)
            elif dac == self.pwm_idx:
                send_dac_fraction(dac, signal * proportion + LU.PWM/255.0)
            
            else:
                #print(f"sent {signal} to {dac}")
                send_dac_fraction(dac, signal * proportion)
                #if dac == 2:
                    #print(signal)

        #send_dac_value(self.pwm_idx, LU.PWM)

        for param in UPDATED_PARAMETERS:  # list updated once per cycle if user has touched physical controls
            #val = self.last_sent.get(param, None)
            #new = PARAMS[param]  # dict lookup because we have the name as a variable here
            try:
                prop_idx = DAC_MAP.index(param)
            except ValueError:
                pass  # some other parameter not associated with a DAC channel
                continue  # nothing to do for now but might use this for envelopes etc
            prop_value = PARAMS[param]
            #print(prop_idx, prop_value.get())
            send_dac_value(prop_idx, prop_value.get())
            # prop_value is a MyVariable, not a straight int
            # TODO: what about modulations!?




        

        

    

# setting up tuning line

TEST_CS_PIN = Pin(27,Pin.OUT,value=1)
TUNE_LATCH_PIN = Pin(26,Pin.OUT,value=1)

# for other testing just always connect the tune bus first thing
time.sleep(0.01)
TEST_CS_PIN.low()  # logical high +12 V on CS
time.sleep(0.01)
TUNE_LATCH_PIN.low()  # rising edge of clock pin
time.sleep(0.01)
TUNE_LATCH_PIN.high()  # falling edge of clock, data is latched
time.sleep(0.01)
TEST_CS_PIN.high()  # data goes low but we saved the bit

send_dac_value(4, 180)  # PWM - 0.70 gives 50% duty
send_dac_value(1, 127)


# define table of note frequencies (midi note index -> frequency)
A1 = 55.00
NOTES = [0.0] * 33  # unused very low notes
# going from A1 as it's the lowest integer number
for x in range(100):
    NOTES.append(round(A1 * 2**(x/12.0),2))
    
# set up envelopes for the voice to use 
BASIC = envelopes.ADSR(100,50,2000,0.7)
SLOW = envelopes.ADSR(50,2000,2000,1.0, inverted=True)
SLOW2 = envelopes.ADSR(200,4000,4000,0.2, inverted=True)
ARONLY = envelopes.ADSR(800,2000,1,0.01)
XFAD = envelopes.ADSR(2500,20,2500,0.5)


MR = MidiReader()
V = Voice()
VOICES = [V]  # in the future, there be more
UPDATED_PARAMETERS = []  # Voice objects will use this list to determine which
# parameters they should refresh by reading in the physical control values
# it's reset every cycle
down_notes = {}  # keep track of which voice is playing which note
 # so we can send key-up signals to them

loop_counter = 0
start_time = time.ticks_us()


DISPLAY.message("Loading...")
PARAMETERS = PhysicalControlsDict()


try: # main loop!
    while 1:
        loop_counter += 1
        #loopstart = time.ticks_us()
        #time.sleep(0.0001)
        MR.read()  # induce the MidiReader to compile messages to read out         
        notes_queue = MR.get_messages("notes")
        controls_queue = MR.get_messages("controls")
        #notes_queue.extend(Y.get(time.ticks_us()))  # testing with hardcoded note seq
        if len(notes_queue) > 1:
            print(notes_queue)
        # this could be lower priority
        if controls_queue:
            for msg in controls_queue:
                chan, value = msg
                print(chan, value)
                retval = PARAMETERS.update_channel(chan, value)
                n, v, refresh = retval  # name, value, should we refresh LCD
                #comment out display cause it's slow
                if refresh:  # we need to change the name of the parameter
                    DISPLAY.clear()
                    DISPLAY.message(n)
                    pass
                if v:
                    DISPLAY.numeric(v)
                    pass
                if n:
                    UPDATED_PARAMETERS.append(n)  # this lets the voice objects know they should re-read the value
        
        for status, note in notes_queue:  # tuples of freq, true/false
            if status:  # True, want to play a new note
                for v in VOICES:  # find the first available voice
                    v.send(False)  # terminate current note
                    down_notes = {}  # can't decay when only 1 voice
                    # TESTING code for single voice case and played note prio.
                    v.send(True, note)
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
            
        UPDATED_PARAMETERS.clear()  # the voice update function handled these
        tnow = time.ticks_us()
        #loop_time = time.ticks_diff(tnow, loopstart)
        #print(f"Loop time is {loop_time} us")
            
        


        """ this loop is for held note priority
        for status, note in notes_queue:  # tuples of freq, true/false
            if status:  # True, want to play a new note
                for v in VOICES:  # find the first available voice
                    if v.note_down:
                        continue  # this voice is already busy
                    freq = NOTES[note]
                    v.send(True, freq)
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
        """


    

finally:
    freq_counter_cleanup()
    send_dac_value(5, 0)  # manually turn off single voice's VCA
    write_params()  # save slider assignments
    for q in VOICES:
        q.osc.save_arrays()


        
