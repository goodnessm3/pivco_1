from machine import Pin
import machine
import time
from freq_count_nodma import get_frequency, freq_counter_cleanup, get_sample, freq_to_count, get_cycle_time, get_sample_reject_anomalies, sample_to_frequency
from mydacs import send_dac_value, dac_setup

dac_setup()

from readmidi import MidiReader
from line_fitter import Fitter

from math import log2, floor 

from oscillator import Oscillator

    
    
def fmt_sample(samp):
    out = ""
    for x, y in samp:
        out += f"{x} {y} "
    return out


# chans: 0 coarse
# 1 fine
# 2 xfade
# 3 sub oct
# 4 yellow aux signal, no, PWM
#send_dac_value(0, random.random())
#5 blue VCA
# 6 red filter res
# 7 blue filter c/0


send_dac_value(0, 65)  # static freq for testing faders

xf = 0.0
su = 0.0
au = 0.0
xfi = 0.04
sui = 0.02
aui = 0.03
pw = 0.5
send_dac_value(1, 127)  # fine - always default to be in middle of range
send_dac_value(2, 0) 
send_dac_value(3, 0) # sub
send_dac_value(4, 227) # PWM now = 0.22 to 1.0 useful range right now
send_dac_value(5, 255)
send_dac_value(6, 192)
send_dac_value(7, 64)

TEST_CS_PIN = Pin(27,Pin.OUT,value=1)
TUNE_LATCH_PIN = Pin(26,Pin.OUT,value=1)
#RST_PIN.high()
#CS_PIN.high()

# YELLOW = DATA LINE
# BLUE = CLOCK LINE
# when a 1 is latched, we measure the freq at the tuning pin
# otherwise, the signal does not get measured (AND gate).
"""
# test code for toggling latch on and off
dataval = 0
for x in range(10):
    time.sleep(1)
    if dataval:
        TEST_CS_PIN.low()  # logical high +12 V on CS
    time.sleep(0.5)
    TUNE_LATCH_PIN.low()  # rising edge of clock pin
    time.sleep(0.5)
    TUNE_LATCH_PIN.high()  # falling edge of clock, data is latched
    # we latched a high so Q1* is low = LED is lit.
    time.sleep(0.5)
    if dataval:
        TEST_CS_PIN.high()  # data goes low but we saved the bit
    time.sleep(0.2)
    time.sleep(1)
    if dataval == 0:
        dataval = 1
    elif dataval == 1:
        dataval = 0
"""

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

MR = MidiReader()
OSC = Oscillator()
OSC.setup()

### TEMP for diagnositcs
"""
A1 = 55.00
NOTES = [0.0] * 33  # unused very low notes
NOTE_WAVECOUNTS = array("I", [0] * 150)
# going from A1 as it's the lowest integer number
for x in range(100):
    freq = round(A1 * 2**(x/12.0),2)
    NOTES.append(freq)  # TODO: this is for diagnostic purposes but not control purposes
    NOTE_WAVECOUNTS[x + 33] = (int(SM_FREQ//freq//2))
    # generates a list where the item at the index of a MIDI note is the
    # frequency of that note, or wavecount to avoid divisions
"""
#### YOu better delete this afterwards!!

try:
    #fine_array = (calibrate_fine_increment())
    
    while 1:
        MR.read()  # induce the MidiReader to compile messages to read out         
        notes_queue = MR.get_messages("notes")
        controls_queue = MR.get_messages("controls")
        #notes_queue.extend(Y.get(time.ticks_us()))
        if len(notes_queue) > 1:
            print(notes_queue)
        for status, note in notes_queue:  # tuples of freq, true/false
            if status:
                #print(note)
                OSC.play_note(note)
    

    

except KeyboardInterrupt:
    freq_counter_cleanup()
    #sm_clocker.active(0)
    #sm_edger.active(0)
    #ma.CTRL_TRIG.EN = 0
    #print("Stopped.")

"""
    for note_index in range(33, 92):
        OSC.play_note(note_index)
        get_sample_reject_anomalies()
        measured_freq = sample_to_frequency(get_sample_reject_anomalies(min_samples=8))
        want = NOTES[note_index]
        error = (measured_freq - want) / want * 100
        print(f"{want}\t{measured_freq}\t{error}")
        
    freq_counter_cleanup()
    print("done")
"""

