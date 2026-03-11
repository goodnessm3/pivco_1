from pin_assignments import *
from machine import Pin, I2C
import time
from voice import Voice
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

V = Voice(tempmodlist, retune=False)
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
        
    


        
