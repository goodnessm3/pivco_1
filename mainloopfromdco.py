from machine import Pin
import time

import envelopes
from readmidi import MidiReader
import math
from freq_count_nodma import freq_counter_cleanup

from mydacs import send_dac_value, dac_setup, send_dac_fraction
dac_setup()  # manages reset pin

from oscillator import Oscillator


def freq2cutoff(freq):
    # what voltage do we need for a cutoff of this freq in Hz?

    freq = freq / 1000.0  # my graph was plotted in kHz
    return (math.log10(freq) - 1.14) / -3.08


class Voice:
    
    def __init__(self):
        
        # setting static values but in future these will be args

        self.osc = Oscillator(0, 1)  # we are manually specifying coarse and fine DAC index here
        # eventually need to give voice an address as well for polyphonic
        self.osc.setup()

        self.xfade_idx = 2
        self.suboctave_idx = 3
        self.pwm_idx = 4
        self.envelope_idx = 5
        self.resonance_idx = 6
        self.cutoff_idx = 7
        
        send_dac_value(self.xfade_idx, 127)
        send_dac_value(self.suboctave_idx, 64)
        send_dac_value(self.resonance_idx, 10)

        
        # current statuses
        self.note_down = False
        self.start_time = time.ticks_ms()  # TODO: shouldn't need this
        # we shouldn't be updating totally idle voices
        
        self.cutoff_freq_tracking = True  # TODO: configurable later
        self.cutoff_mod = 0.0  # emulate CV to volts/octave cutoff. Add this
        # to whatever else is modulating the COF.
        self.cutoff_base = -0.45  # how far offset the COF signal is from the osc freq
        # a negative cutoff base -> higher cutoff freq
        self.resonance_base = 0.9
        
        self.envelope_assignments = [
                                    (self.envelope_idx, BASIC, 1.0 ),
                                     (self.cutoff_idx, BASIC, 0.55),
                                     #(self.resonance_idx, BASIC, 0.3),
                                     #(self.xfade_idx, SLOW, 1.0)
                                    ]
        # which properties are modulated by the envelope?
        # and to what extent? Tuples of (DAC channel, env, scaling factor)
        

            
    def set_mixture(self, fraction):
        
        # proportion of waveform
        
        send_dac_fraction(self.xfade_idx, fraction)
        
    def set_cutoff_base(self, ctrl):
        
        self.cutoff_base = ctrl/127.0 - 0.5
        # TODO: 8 bit
        # TODO: sort out scaling, centre point etc
        #print(f"Cutoff freq was set to {ctrl/127.0}")
        
    def set_resonance_base(self, ctrl):
        
        self.resonance_base = ctrl/127.0

    
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
                
                if self.cutoff_freq_tracking:
                    self.cutoff_mod = freq2cutoff(freq)
                    send_dac_fraction(self.cutoff_idx, self.cutoff_mod + self.cutoff_base)
                    
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
        
        for dac, env, proportion in self.envelope_assignments:
            signal = env.get_level(timedelta, self.note_down)
            if dac == self.cutoff_idx:
                send_dac_fraction(dac, (signal * proportion) + self.cutoff_mod + self.cutoff_base)
                # special case for now: cutoff freq tracks oscillator freq
            elif dac == self.resonance_idx:
                send_dac_fraction(dac, signal * proportion + self.resonance_base)
            else:
                #print(f"sent {signal} to {dac}")
                send_dac_fraction(dac, signal * proportion)
                #if dac == 2:
                    #print(signal)

    

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
BASIC = envelopes.ADSR(100,50,100,0.7)
SLOW = envelopes.ADSR(4000,100,4000,1.0, inverted=True)
ARONLY = envelopes.ADSR(800,2000,1,0.01)
XFAD = envelopes.ADSR(2500,20,2500,0.5)


MR = MidiReader()
V = Voice()
VOICES = [V]  # in the future, there be more
down_notes = {}  # keep track of which voice is playing which note
 # so we can send key-up signals to them

loop_counter = 0
start_time = time.ticks_us()

CONTROLS = {
            
            73: V.set_cutoff_base,
            74: V.set_resonance_base
            }
# mapping of what keyboard control does what, look up the method from this dict
# and then invoke it with the control signal as an argument



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
                func = CONTROLS[chan]
                func(value)
        
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
    for q in VOICES:
        q.osc.save_arrays()


        
