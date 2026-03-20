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

ADDRESS_MANAGER.put(0)  # !!!!!!!!!!! for testing new card!!!!
prepare_tune_latch()  # just latch something to start off with
time.sleep(0.1)  # make sure the latch state machine is ready to recieve the rising edge of AEN

for x in range(2):  # !!!!!!!! TEMP - this is the number of voices, each must be setupped
    ADDRESS_MANAGER.put(x)
    time.sleep(0.1)
    dac_setup()  # manages reset pin


# IMPORTANT! These need to be imported AFTER dac setup. But why????
from voice import Voice
from dac_manager import DacManager
# if they are imported before, then the tuning latch doesn't work???

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

# these are the modulations for each of 6 voices, channels 1-8 on the DAC. The offset is the voice number
# so index // 8 is voice, index % 8 is the dac channel.
modulation_array = array("B", [0] * 48)
update_masks = array("B", [0] * 8)
# which DAC parameters changed? This is a bitmask, so 00001000 -> only change that channel
active_voices = 0  # bitmask








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




ADDRESS_MANAGER.put(0)
V = Voice(0, tempmodlist, modulation_array_reference=modulation_array, retune=False)
prepare_tune_latch()
ADDRESS_MANAGER.put(1)
VV = Voice(1, tempmodlist, modulation_array_reference=modulation_array, retune=False)
#!!! ADDR!!!
V.monitoring = False  # TODO: handle monitoring of multiple voices
VV.monitoring = False
VOICES = [V, VV]  # in the future, there be more
# voices must appear in this list in ascending address order for the address manager to work

MR = MidiReader()
CONTROLS = Controls(VOICES, LFOLIST, ADSRLIST)
DM = DisplayManager(VOICES, LFOLIST, ADSRLIST)
#DAC_MANAGER = DacManager(modulation_array, 1)  # todo: active voices should be a bitmask

print("Loading saved settings...")
settings_manager.load_object_settings(VOICES, ADSRLIST, LFOLIST)
print("Done")

HELD_NOTES = array("B", [0] * 97)  # keep track of which voice is playing which note
 # so we can send key-up signals to them
 # index = midi note, value = the voice that is playing the note
CURRENT_NOTES = array("B", [0] * 8)  # which note is played by which voice?


loopcount = 0
loopstart = time.ticks_ms()

# 96 is the highest MIDI note on the keyboard
#settings_manager.save_object_settings(VOICES, ADSRLIST, LFOLIST)

#NEXT_VOICE = 0  # the address of where we will send the newest note. Increments and loops around.
#VOICE_COUNT = len(VOICES)
VOICE_COUNT = 2

from collections import deque
VOICE_USE = deque([], 8)

# arbitrarily order the voices into the deque so they all appear once
VOICE_USE.append(0)
VOICE_USE.append(1)  # TODO - decent start but need better voice assignment algorithm that picks an unused voice

try:
    while 1:

        #DAC_MANAGER.update()
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
                #print(msg)
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
                NEXT_VOICE = VOICE_USE.popleft()
                VOICES[NEXT_VOICE].send(True, note)
                HELD_NOTES[note] = NEXT_VOICE  # store the address so we can "un-play" this note on key up
                CURRENT_NOTES[NEXT_VOICE] = note
                VOICE_USE.append(NEXT_VOICE)  # so we can keep a record of which key was least recently pressed
                print("sent note on to voice ", VOICES[NEXT_VOICE])
                print("deque ", VOICE_USE)

            else:  # TODO - just do it better OK
                addr = HELD_NOTES[note]
                if CURRENT_NOTES[addr] == note:
                    VOICES[addr].send(False)  # only need to do this if the voice didn't get stolen in the meantime
                    # we don't want to prematurely terminate the stolen note.
                HELD_NOTES[note] = 0
                print("Send note off to voice ", addr)

            #NEXT_VOICE += 1  # todo - what if one note held and others come on and off, need to be cleverer

            #if NEXT_VOICE >= VOICE_COUNT:
                #NEXT_VOICE = 0  # wrap and start re-using voices if all are occupied


                """
                for v in VOICES:  # find the first available voice
                    v.send(False)  # terminate current note
                    down_notes = {}  # can't decay when only 1 voice
                    # this is TESTING code for single voice case and played note prio.
                    v.send(True, note)
                """


                    #!!!!!!!!!!!!!!!!!!!!!!!
                    #v.monitoring = True  # TODO - track which notes are monitored
                    #!!!!!!!!!!!!!!!!!!!!!!!



                    #print(f"Assigned note {note} to {v}")
                    #down_notes[note] = v  # keep a reference so we can unplay note

                    # !!!!!!!!!!!!!! remove break to play both at once



            """        
            else:  # False, meaning note up
                voice = down_notes.get(note, None)
                # there might be a note up signal for an uplayed note
                # if we ran out of voices to allocate, so just skip it.
                if voice:
                    voice.send(False)  # free up voice
                    #print(f"freeing voice {voice}")
            """

        for i in range(VOICE_COUNT):
            #print("address update ", i)
            ADDRESS_MANAGER.put(i)
            VOICES[i].update()
            # todo - need to update when decaying, but want to avoid when absolutely nothing happening
        #for q in VOICES:
            #q.update()


finally:
    print("count", loopcount)
    total_time = time.ticks_diff(time.ticks_ms(), loopstart)

    lps = loopcount / total_time * 1000
    print(f"Averaged {lps} loops per second over {total_time} ms.")
    freq_counter_cleanup()
    send_dac_value(5, 0)  # manually turn off single voice's VCA
    print("cleaned up freq counter and muted VCA, starting file saving")
    try:  # in testing with Thonny, sometimes we will get a second keyboard interrupt during the file writing
        # seems intermittent, at least we can detect when it happens.
        settings_manager.save_object_settings(VOICES, ADSRLIST, LFOLIST)


        for q in VOICES:
            q.osc.save_arrays()
    except KeyboardInterrupt:
        print("saving recieved another interrupt and may have failed")
    print("bottom of finally block")


        
    


        
