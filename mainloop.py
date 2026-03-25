from pidcontroller import PidController
from pin_assignments import *
from machine import Pin, I2C
import time
from sys import exit
import _thread
from fastlog2 import fast_log2
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
from freq_count_nodma import freq_counter_cleanup, freq_count_reset, get_frequency_ema, reset_ema
from mydacs import send_dac_value, dac_setup, ADDRESS_MANAGER, prepare_tune_latch
from wavecount_table import NOTE_WAVECOUNTS  # use this to give the tuning PIDs a target
# this table actually contains the log2s of the wave counts

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

VOICES = [V, VV]  # in the future, there be more
# voices must appear in this list in ascending address order for the address manager to work

MR = MidiReader()

DM = DisplayManager(VOICES, LFOLIST, ADSRLIST)
#DAC_MANAGER = DacManager(modulation_array, 1)  # todo: active voices should be a bitmask

print("Loading saved settings...")
settings_manager.load_object_settings(VOICES, ADSRLIST, LFOLIST)
print("Done")

HELD_NOTES = array("b", [-1] * 97)  # keep track of which voice is playing which note
 # so we can send key-up signals to them
 # index = midi note, value = the voice that is playing the note
 # -1 means no voice is playing that note. Obviously can't use a default of 0 because that is a real address
CURRENT_NOTES = array("B", [0] * 8)  # which note is played by which voice?

RUNNING = False
loopcount = 0
loopstart = time.ticks_ms()

# 96 is the highest MIDI note on the keyboard
#settings_manager.save_object_settings(VOICES, ADSRLIST, LFOLIST)

#NEXT_VOICE = 0  # the address of where we will send the newest note. Increments and loops around.
#VOICE_COUNT = len(VOICES)
VOICE_COUNT = 2

from collections import deque
#VOICE_USE = deque([], 8)  # voices that are currently in use
AVBL_VOICES = deque([], 8)  # voices that are not gating, but still might be decaying after note off. Prefer using
# one of these rather than stealing an active voice, and if we do take from this deque, take the oldest entry which
# will be the most decayed
# arbitrarily order the voices into the deque so they all appear once
AVBL_VOICES.append(0)
AVBL_VOICES.append(1)
#print("deque ", list(AVBL_VOICES))

def shut_down():

    global RUNNING

    RUNNING = False

    print("Shutting down...")
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
    print("Shutdown function finished")
    exit()


CONTROLS = Controls(VOICES, LFOLIST, ADSRLIST, shut_down)  # needs to be instantiated after shutdown func defined

# arrays for the PID tuning core to read targets and apply corrections
#TARGET_WAVETIME_ARRAY = array("I", [0] * 8)  # this is written to by the main loop
# don't need - specify PID setpoints directly
# 0 = coarse, 1 = fine, 2 = coarse, 3 = fine etc
CORRECTIONS_ARRAY = array("B", [0] * 16)
MEASURED_ADDRESS = 0  # the address we are monitoring on the tune bus
LATCH_PREPARED = False
P = 1500
I = 500
D = 100
PIDLIST = [PidController(P, I, D), PidController(P, I, D)]
# for setting up tuning. 4000, 186, 2000
COARSELIST = [V.osc.coarse_array, VV.osc.coarse_array]
FINELIST = [V.osc.fine_array, VV.osc.fine_array]
# TODO: magic numbers!!!!!!!!!! Centralize PID settings

def tune_loop(corrections_array, get_frequency_func, reset_ema_func):

    global RUNNING
    global MEASURED_ADDRESS
    global TARGET_WAVETIME_ARRAY
    global LATCH_PREPARED
    global COARSELIST
    global FINELIST
    global PIDLIST

    ALPHA = 1024  # for EMA of pid corrections
    EMA = 0

    fast_counter = 0
    fast_start_time = time.ticks_ms()
    corrections_array = corrections_array
    get_frequency_ema = get_frequency_func  # really not sure if we needed to pass it in like this but got name errors
    reset_ema = reset_ema_func

    print("Tuning loop started on separate core.")
    cnt = 0
    coarse_jump = 0  # only change coarse increment if we tried to send multiple out-of-range fine signals
    prev_note = array("B", [0] * 8)
    target_wavecount_array = array("I", [0] * 8)
    # if the setpoint changed, we want to reset the frequency measurer otherwise our correction
    # will be based on old frequency samples
    cycles_since_change = 0
    cycles_since_address_incremented = 0  # only permit corrections after a certain number of cycles
    cycles_correction_allowed = 0  # wait this many cycles before issuing any corrections
    # to give freq and output voltages time to stabilize

    def reset_measurement():

        time.sleep(0.1)
        reset_ema()
        freq_count_reset()
        note = prev_note[MEASURED_ADDRESS]
        PIDLIST[MEASURED_ADDRESS].reset(note)

    # parameters for smoothing out the measured correction signal and determining if a note is tuned, converges to 0
    ERROR_EMA = 0
    ERROR_ALPHA = 256


    while 1:
        if RUNNING:
            freq, stale = get_frequency_ema(min_samples=1)  # TODO <----- probably decrease this a bit?? OR change alpha
            logfreq = fast_log2(freq)

            # waiting loops - for new audio sample or for address to change
            while stale:
                freq, stale = get_frequency_ema()  # poll until we measured a new wave cycle and updated the measurement
            while not LATCH_PREPARED:
                time.sleep(0.01)
                pass  # we asked to measure a different voice, need to wait for the main loop to reach the update part

            if not logfreq:
                continue  # don't care if EMA returned 0 (todo - why does it sometimes return 0?)

            pid = PIDLIST[MEASURED_ADDRESS]
            note = CURRENT_NOTES[MEASURED_ADDRESS]  # find out what the measured voice is supposed to be playing

            if not note == prev_note[MEASURED_ADDRESS]:
                # bail early because the target note has changed and our correction is outdated
                cycles_since_change = 0
                prev_note[MEASURED_ADDRESS] = note
                target_wavecount = NOTE_WAVECOUNTS[note]
                target_wavecount_array[MEASURED_ADDRESS] = target_wavecount
                # avoids big jumps in PID output
                reset_ema()  # start EMA off with a dummy value that is what we want to measure
                freq_count_reset()
                pid.setpoint = NOTE_WAVECOUNTS[note]
                pid.reset(note)  # passing a note to this method recalls the previous accumulated error for that note
                continue

            corxn = pid.get_correction(logfreq)
            error = pid.get_error()
            ERROR_EMA = ((ERROR_ALPHA * error) >> 12) + (((4096 - ERROR_ALPHA) * ERROR_EMA) >> 12)

            if cycles_since_address_incremented > cycles_correction_allowed:
                FINELIST[MEASURED_ADDRESS][note] = corxn + 127  # correct that voice's tuning table
            # !?!?!?!?!??! offset!?!??!  this seems to make it work a lot better!?!?!?!?!?!


            if corxn > 128 and cycles_since_change > 20:  # only permit coarse changes after some considerable time
                coarse_jump += 1
                if coarse_jump > 3:
                    COARSELIST[MEASURED_ADDRESS][note] += 1
                    coarse_jump = 0
                    pid.reset()
            elif corxn < -127 and cycles_since_change > 20:
                coarse_jump += 1
                if coarse_jump > 3:
                    COARSELIST[MEASURED_ADDRESS][note] -= 1
                    coarse_jump = 0
                    pid.reset()

            # for plotting graphs
            #print(f"{corxn}\t{PIDLIST[MEASURED_ADDRESS].setpoint}\t{logfreq}")

            fast_counter += 1
            cycles_since_change += 1
            cycles_since_address_incremented += 1


            #print(ERROR_EMA)

            cnt += 1
            #if cnt > 200:  # 1000 measurements, increment voice we are measuring
            print(ERROR_EMA)
            #print(MEASURED_ADDRESS)
            if -10 < ERROR_EMA < 10:  # consider the note tuned and move on
                # not this error is a number of clock cycles counted per wave cycle.
                ERROR_EMA = 20  # fudge factor to force collection of some measurements
                MEASURED_ADDRESS += 1
                if MEASURED_ADDRESS > 1:
                    MEASURED_ADDRESS = 0
                LATCH_PREPARED = False
                cnt = 0
                reset_measurement()  # don't want new note contaminated with measurements from other one
                cycles_since_change = 0  # suppress coarse changes

                #time.sleep(0.2)

        else:
            break

    print("Tuning loop exited via running flag")
    end_time = time.ticks_ms()
    delta = time.ticks_diff(end_time, fast_start_time)
    rate = fast_counter/delta * 1000
    print(f"fast loop: {fast_counter} cycles in {delta} ms: {rate} per second.")
    print("-------> second core exited cleanly")
    #finally:
        #print("Exited DAC loop via keyboard interrupt")

RUNNING = True
_thread.start_new_thread(tune_loop, (CORRECTIONS_ARRAY, get_frequency_ema, reset_ema))


try:
    while 1:
        #print(TARGET_WAVETIME_ARRAY)
        #print("measured address ", MEASURED_ADDRESS)
        #print("top of main loop")
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
                #print(ret)
                if not ret:
                    continue  # should this be break?
                for tup in ret:
                    ob, parm, value = tup
                    if parm:  # write the named variable of the specified object
                        # ob.__setattr__(parm, value)  # not this!!
                        setattr(ob, parm, value)  # but this!!
                    pair = DM.update(tup)  # get a new frame buffer for the LCD
                    DISPLAY.update(pair)  # send the new frame buffer for display next loop

        for status, note in notes_queue:  # tuples of freq, true/false

            if status:  # True, want to play a new note
                try:
                    NEXT_VOICE = AVBL_VOICES.popleft()
                except IndexError as e:
                    #print("no free voice available")
                    continue
                VOICES[NEXT_VOICE].send(True, note)
                HELD_NOTES[note] = NEXT_VOICE  # store the address so we can "un-play" this note on key up
                CURRENT_NOTES[NEXT_VOICE] = note
                pid = PIDLIST[NEXT_VOICE]



            else:
                addr = HELD_NOTES[note]
                if addr == -1:
                    pass  # this note isn't actually being played, shouldn't be able to get here??
                if CURRENT_NOTES[addr] == note:
                    VOICES[addr].send(False)  # only need to do this if the voice didn't get stolen in the meantime
                    # we don't want to prematurely terminate the stolen note.
                    HELD_NOTES[note] = 0
                    #print("Send note off to voice ", addr)
                    AVBL_VOICES.append(addr)  # mark as available for a new note



        for i in range(VOICE_COUNT):
            #print("address update ", i)
            if i == MEASURED_ADDRESS:
                if not LATCH_PREPARED:
                    prepare_tune_latch()  # switch to measuring this voice on the next CS toggle
                    LATCH_PREPARED = True  # need this to only fire once, otherwise we'll fill up the FIFO of the
                    # latch manager and it will block
            ADDRESS_MANAGER.put(i)
            VOICES[i].update()
            # todo - need to update when decaying, but want to avoid when absolutely nothing happening

except Exception as e:
    print(repr(e))

finally:
    shut_down()


        
    


        
