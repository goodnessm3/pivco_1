from machine import Pin
import machine
import time
from freq_count_nodma import get_frequency, freq_counter_cleanup, get_sample, freq_to_count, get_cycle_time, get_sample_reject_anomalies
from mydacs import send_dac_value, dac_setup
dac_setup()

from readmidi import MidiReader
from line_fitter import Fitter

from math import log2, floor 


A1 = 55.00
NOTES = [0] * 33  # unused very low notes
# going from A1 as it's the lowest integer number
for x in range(100):
    NOTES.append(round(A1 * 2**(x/12.0),2))
    # generates a list where the item at the index of a MIDI note is the
    # frequency of that note


# frac 0.1, on 1 and 4
# 0.2: 1, 2, 6
#0.3: 3 full, 4
#0.4: 2, 3 full, 6


# 241 is 11110001 - addresses shift regs 2,3 and 4 (1 unused now)
# DAC 1 = top of row = 2
# DAC 2: 4
# DAC 3: 8 (middle DAC)
# 14 ^ 255 = 241

# from top to bottom:
# integrator -side, int +side, VCA, xfade, c/o, resonance
# 0: int-, 1: int+, 2:VCA, 3:xfade, 4:co, 5:res
# outA - top of DAC - 0 (dacB: write 1)

# SM1 = pin 14 = + side integrator (DAC 1)
####################

        
############## main looop start

# setting up serial hardware





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

#send_dac_value(1, 1.0)

# DACS 0.43 and 0.90 for middle C

from math import log2

def long_measurement(cnt=20, sl=0.4):
    
    tot = 0
    for x in range(cnt):
        time.sleep(sl)
        tot += get_cycle_time()
    return tot

    



"""
send_dac_value(1, 127)  # fine voltage at 1/2 maximum
for v in range(32, 256, 64):
    # 4 points for tuning curve
    send_dac_value(0, v)
    c = long_measurement(cnt=10)
    print(v, c//10)
    T1.add(v, c//10)  # divide by 20 because we took 20 measurements
    
T1.fit_line()

desired_cnt = freq_to_count(261.63)
print(desired_cnt)
print(T1.clocks_to_voltage(desired_cnt))
"""
def fmt_sample(samp):
    out = ""
    for x, y in samp:
        out += f"{x} {y} "
    return out

def longer_sample(pts=40, sleep_time=0.2):
    
    points = 0
    xtot = 0
    ytot = 0
    
    while points < pts:
        time.sleep(sleep_time)
        hi, lo, tot = get_sample_reject_anomalies()
        points += tot
        xtot += hi
        ytot += lo
        
    return xtot, ytot, points

def sample_to_frequency(smp, clk_freq=6_000_000):
    
    hi, lo, counts = smp
    return clk_freq * counts / (hi + lo) / 2

def note_to_dac_signals(note, fit_obj):
    
    want = NOTES[note]
    dacsignal = fit_obj.getx(log2(want))
    #print(f"want {dacsignal} for {want}")
    cors = floor(dacsignal)
    #fine_increment_here = fine_array[cors//16]
    fine_increment_here = 0.005
    fin = floor((dacsignal - cors) / fine_increment_here)
    
    return cors, fin

# TODO - consolidate tehese

def freq_to_dac_signals(want, fit_obj):
    
    dacsignal = fit_obj.getx(log2(want))
    #print(f"want {dacsignal} for {want}")
    cors = floor(dacsignal)
    #fine_increment_here = fine_array[cors//16]
    fine_increment_here = 0.005
    fin = floor((dacsignal - cors) / fine_increment_here)
    
    return cors, fin

def volt_to_dac_signals(dacsignal, fit_obj):
    
    cors = floor(dacsignal)
    #fine_increment_here = fine_array[cors//16]
    fine_increment_here = 0.005
    fin = floor((dacsignal - cors) / fine_increment_here)
    
    return cors, fin


send_dac_value(4, 180)  # PWM - 0.70 gives 50% duty
MR = MidiReader()
F1 = Fitter()  # coarse voltages


# send in the error measurements to a second tuner object
for q in (32,96,150,200,220):
    send_dac_value(0, q)
    time.sleep(0.01)
    get_sample()  # throw away stale data
    time.sleep(0.2)
    r = longer_sample()
    F1.add(q, log2(sample_to_frequency(r)))
    
F1.fit_line()
print("fitted initial line")
print(F1.m, F1.c)

print("fitting correction factor - low frequencies")
F2 = Fitter(difference_threshold=0.0001)  # establish correction factor, lo freqs
for note in 35, 40, 44, 55, 66:
# now work out the second order correction
# using actual notes at lower frequencies < 400 Hz
    c,f = note_to_dac_signals(note, F1)
    send_dac_value(0, c)
    send_dac_value(1, f)
    time.sleep(0.01)
    get_sample()
    time.sleep(0.2)
    measured = sample_to_frequency(longer_sample())
    expected = NOTES[note]
    error = (measured-expected)/expected  # percent error
    F2.add(log2(expected), error)  # now we can predict the error and compensate
    print(f"measured: {measured} expected: {expected} error: {error}%")
    
print("fitting correction factor - high frequencies")
F3 = Fitter(difference_threshold=0.0001)  # establish correction factor, high freqs
for note in 66, 72, 78, 84, 92:
# using actual notes at lower frequencies > 400 Hz
    c,f = note_to_dac_signals(note, F1)
    get_sample()
    send_dac_value(0, c)
    send_dac_value(1, f)
    time.sleep(0.01)
    get_sample()
    time.sleep(0.2)
    measured = sample_to_frequency(longer_sample())
    expected = NOTES[note]
    error = (measured-expected)/expected  # percent error
    F3.add(log2(expected), error)  # now we can predict the error and compensate
    print(f"measured: {measured} expected: {expected} error: {error}%")
    
    
F2.fit_line()
F3.fit_line()
    
    
def get_corrected_dac_values(note, rough, locorr, hicorr):
    """
    freq = NOTES[note_index]
    logfreq = log2(freq)
    if freq > 400:
        correction_factor = hicorr.gety(logfreq)
    else:
        correction_factor = locorr.gety(logfreq)
        
    #print(f"Correction factor for {freq}: {correction_factor}")
    corrected = freq * (1 - correction_factor)
    c, f = freq_to_dac_signals(corrected, F1)
    return c, f
    """
    freq = NOTES[note_index]
    logfreq = log2(freq)
    if freq > 400:
        correction_factor = hicorr.gety(logfreq)
    else:
        correction_factor = locorr.gety(logfreq)
        
    naive_voltage = F1.getx(logfreq)
    #print(f"naive_volrage {naive_voltage}")
    #print(f"corxn factor {correction_factor}")
    corrected = naive_voltage * (1- correction_factor)
        
    c, f = volt_to_dac_signals(corrected, F1)

    return c, f

try:
    #fine_array = (calibrate_fine_increment())
    
    note_index = 33

    print("checking tuning accuracy")
    
    while note_index < 95:
        """
        want = NOTES[note_index]
        dacsignal = F1.getx(log2(want))
        #print(f"want {dacsignal} for {want}")
        cors = floor(dacsignal)
        #fine_increment_here = fine_array[cors//16]
        fine_increment_here = 0.005
        fin = floor((dacsignal - cors) / fine_increment_here)
        print(f"will send {cors} and {fin}")
        """
        cors, fin = get_corrected_dac_values(note_index, F1, F2, F3)
        want = NOTES[note_index]
        #cors, fin = note_to_dac_signals(note_index, F1)
        
        send_dac_value(0, cors)
        send_dac_value(1, fin)
        time.sleep(0.01)
        get_sample_reject_anomalies()
        time.sleep(0.2)
        measured_freq = sample_to_frequency(longer_sample())
        error = (measured_freq - want) / want * 100
        #print(f"Desired: {wantff} measured: {measured_freq} error: {error}%")
        print(f"{want}\t{measured_freq}\t{error}")
        note_index += 1
    """
    wanted = None
    status = None
    while True:
        
        MR.read()
        m = MR.get_messages("notes")
        print(m)
        
        for status, note in m:
            wanted = NOTES[note]
            if wanted:
                dacsignal = F1.getx(log2(wanted))
                #print(f"want {dacsignal} for {want}")
                cors = floor(dacsignal)
                #fine_increment_here = fine_array[cors//16]
                fine_increment_here = 0.0052
                fin = floor((dacsignal - cors) / fine_increment_here)
                #print(f"will send {cors} and {fin}")
                
                send_dac_value(0, cors)
                send_dac_value(1, fin)
                
                
        measured_freq = sample_to_frequency(get_sample_reject_anomalies())
        print(f"Measured: {measured_freq} wanted: {wanted}")
        time.sleep(0.1)
"""



except KeyboardInterrupt:
    freq_counter_cleanup()
    #sm_clocker.active(0)
    #sm_edger.active(0)
    #ma.CTRL_TRIG.EN = 0
    #print("Stopped.")


