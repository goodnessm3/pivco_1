from machine import Pin
import machine
import time
from freq_count_nodma import get_frequency, freq_counter_cleanup, get_sample, freq_to_count, get_cycle_time, get_sample_reject_anomalies
from mydacs import send_dac_value, dac_setup
dac_setup()

from readmidi import MidiReader
from line_fitter import Fitter

from math import log2, floor 

SM_FREQ = 6_000_000


A1 = 55.00
NOTES = [0] * 33  # unused very low notes
NOTE_WAVECOUNTS = [0] * 33
# going from A1 as it's the lowest integer number
for x in range(100):
    freq = round(A1 * 2**(x/12.0),2)
    NOTES.append(freq)
    NOTE_WAVECOUNTS.append(int(SM_FREQ//freq//2))
    # generates a list where the item at the index of a MIDI note is the
    # frequency of that note, or wavecount to avoid divisions
    
    
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
    
    return cors


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

from math import log2

def long_measurement(cnt=20, sl=0.4):
    
    tot = 0
    for x in range(cnt):
        time.sleep(sl)
        tot += get_cycle_time()
    return tot



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


send_dac_value(4, 180)  # PWM - 0.70 gives 50% duty
send_dac_value(1, 127)
# do initial tuning with half fine adjustment so that we always have "wiggle room"
# for the fine tuning
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


class PidController:
    
    def __init__(self):
        
        self.accumulated_error = 0
        self.p = 2  # note these are bit shifts, so 3 means divide by 8
        self.d = 3
        self.i = 4
        self.instantaneous_error = 0
        
    def reset(self):
        
        self.accumulated_error = 0
        self.instantaneous_error = 0
        
    def get_correction(self, note):

        #print("accu error: ", self.accumulated_error)
        hi, lo, count = get_sample_reject_anomalies(min_samples=3)  # returns 2 wave cycles and how many measuemntes
        measured = (hi + lo)//count
        desired = NOTE_WAVECOUNTS[note]
        delta = desired - measured
        self.accumulated_error += delta
        self.instantaneous_error = delta
        
        correction = (delta >> self.p) + (self.accumulated_error >> self.i) - (delta >> self.d)
        #print("P",delta >> self.p)
        #print("D",delta >> self.d)
        #print("I",self.accumulated_error >> self.i)
        #print(f"Measured: {measured} desired: {desired} delta: {delta} corrextion: {correction}")
        
        return -1 * correction  # so hard to keep track of signs
    
    def get_error(self):
        
        return self.instantaneous_error

    
PID = PidController()
COARSE_ARRAY = [0] * 250
FINE_ARRAY = [0] * 250

try:
    #fine_array = (calibrate_fine_increment())
    
    note_index = 33
    
    while note_index < 95:
        print("checking tuning accuracy")
        corxn = 1000
        error = 100
        corr = 0
        test_note = note_index
        want = NOTES[note_index]
        coarse = note_to_dac_signals(test_note, F1)  # uses line fit and floats
        print(f"for note {note_index} sending {coarse} to dac")
        print("step\terror\tcorrection")
        send_dac_value(0, coarse)
        send_dac_value(1, 127)  # start by centering fine
        inc = 0
        err = 999  # arbitrary to start loop
        while abs(err) > 15:
            #print(f"tuning note {note_index}")
            if corr > 255:  # fine is 1/200th of coarse and need to prevent overlap
                #print("coarse + 1")
                coarse += 1
                send_dac_value(0, coarse)
                send_dac_value(1, 127)  
            elif corr < 0:
                #print("coarese - 1")
                coarse -= 1
                send_dac_value(0, coarse)
                send_dac_value(1, 127)
            else:
                #print(f"sending {corr} to fine")
                send_dac_value(1, corr)
                
            get_sample_reject_anomalies()  # discard old values
            #time.sleep(0.2)
            
            #measured_freq = sample_to_frequency(longer_sample())
            #error = (measured_freq - want) / want * 100
            #time.sleep(0.1)
            #print(f"{want}\t{measured_freq}\t{error}%")
            #print("---")
            corxn = PID.get_correction(note_index)
            err = PID.get_error()
            corr = 127 + corxn
            #print(f"calculated correction: {corxn}")
            print(f"{inc}\t{err}\t{corxn}")
            inc += 1
        COARSE_ARRAY[note_index] = coarse
        FINE_ARRAY[note_index] = corr
            
            
            #time.sleep(1)
            
        inc = 0
        print(f"converged for note {note_index}")
        note_index += 1
        PID.reset()
        
    print("tuning complete, checking notes")
    print(f"target freq\tmeasured\terror(%)")
    for note_index in range(33, 92):
        c = COARSE_ARRAY[note_index]
        f = FINE_ARRAY[note_index]
        send_dac_value(0, c)
        send_dac_value(1, f)
        get_sample_reject_anomalies()
        #time.sleep(0.1)
        measured_freq = sample_to_frequency(get_sample_reject_anomalies(min_samples=8))
        want = NOTES[note_index]
        error = (measured_freq - want) / want * 100
        print(f"{want}\t{measured_freq}\t{error}")
        
    freq_counter_cleanup()
    print("done")
    
    """while note_index < 95:

        coarse = note_to_dac_signals(note_index, F1)  # uses line fit and floats
        print(f"for note {note_index} sending {coarse} to dac")
        
        send_dac_value(0, coarse)
        time.sleep(0.01)
        get_sample_reject_anomalies()
        time.sleep(1)
        want = NOTES[note_index]
        measured_freq = sample_to_frequency(longer_sample())
        error = (measured_freq - want) / want * 100
        time.sleep(1)
        #print(f"Desired: {wantff} measured: {measured_freq} error: {error}%")
        print(f"{want}\t{measured_freq}\t{error}")
        print("---")
        get_correction(note_index)
        time.sleep(5)
        
        note_index += 1"""
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


