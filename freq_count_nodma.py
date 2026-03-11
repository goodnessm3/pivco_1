from pin_assignments import *
import time, array, uctypes, machine, struct
import rp2
from rp2 import PIO, asm_pio
# !!!!!!!!!
# IMPORTANT
# UART(0, ... seems to conflict with the PIO blocks
# MIDI reading MUST be done using UART 1 instead
# !!!!!!!!!

# ==========================================
# 1. PIO Configuration (Robust Timing)
# ==========================================

SM_FREQ = 6_000_000
MAXX = 2**16-1
EMA = 0  # module-level exponential moving average value
DUTY_CYCLE = 0  # exponential moving average of wave duty cycle to make PWM setting more accurate  # TODO
ALPHA = 768  # parameter that determines the smoothness of the ema: lower = smoother but more laggy
# 2048 good at 21:40

# CHANGED 22:12 - in_ instead of mov to isr  was mov(isr, x)
# also fixed MAXXX to have -1
# 22:16 Autopush instead of explicit push
# replaced line: push(noblock)      # Send to FIFO
@asm_pio(autopush=True, fifo_join=PIO.JOIN_RX)  # RX FIFO will be pushed to when we have 2 16-bit values
def clocker():
    #pull(noblock)      # Load max counter value to OSR
    mov(x, invert(null))        # Reset Counter
    wrap_target()
    label("count")
    jmp(pin, "write")  # Check sync pin
    jmp(x_dec, "count")
    label("write")
    #mov(isr, x)        # Capture count
    in_(x, 16)
    #push(noblock)
    mov(x, invert(null))        # Reset Counter immediately
    wait(0, pin, 0)    # Wait for sync low
    wrap()
    
# we want to use in rather than mov to put fewer bytes into the ISR at a time.

@asm_pio(sideset_init=PIO.OUT_LOW)
def edge_watcher():
    wrap_target()
    wait(1, pin, 0)
    nop().side(1) [3]  # Pulse High for 3 cycles
    nop().side(0)
    wait(0, pin, 0)
    nop().side(1) [3]  # Pulse High for 3 cycles
    nop().side(0)
    wrap()

# Pin Setup
gppin = machine.Pin(P_TUNE_INPUT, machine.Pin.IN, machine.Pin.PULL_UP)
sidepin = machine.Pin(P_PIN_SYNC, machine.Pin.OUT)
sidepin.value(0)

# 22:05 - back to old clocker sm
sm_clocker = rp2.StateMachine(0, clocker, freq=SM_FREQ, jmp_pin=sidepin)
sm_edger = rp2.StateMachine(1, edge_watcher, freq=SM_FREQ, in_base=gppin, sideset_base=sidepin)

#sm_clocker.put(0xFFFF)
sm_clocker.active(1)
sm_edger.active(1)



def get_sample():
    
    out = []
    first = True

    while sm_clocker.rx_fifo() > 0:
        if first:
            d = sm_clocker.get()  # sadly have to throw away first measurement
            first = False
            continue
        d = sm_clocker.get()
        v1 = d >> 16
        v2 = d & 0xFFFF  # splitting 32-bit number into 2 16-bit numbers
        v3 = MAXX - v1  # we were decrementing the counter, so need to subtract from max val to get elapsed clock cycles
        v4 = MAXX - v2
        
        out.append((v3, v4))
        
    return out


def get_sample_reject_anomalies(blocking=True, min_samples=1):
    
    """If blocking, will always wait for at least one sample to be available.
    otherwise, it can return None. (This will cause errors if whoever is
    calling it expects a sample"""

    last = None
    measurements = 0
    xtot = 0
    ytot = 0
    first = True
    
    while sm_clocker.rx_fifo() < min_samples-1:  # we asked for a sample but there isn't one yet!
        #  < 2 because we always discard the first sample
        if not blocking:
            return  # just bail and return no sample
        time.sleep(0.001)  # emerge from this loop as soon as there is a sample
    
    while sm_clocker.rx_fifo() > 0:
        if first:
            d = sm_clocker.get()  # sadly have to throw away first measurement
            first = False
            continue
        
        d = sm_clocker.get()
        x = MAXX - (d >> 16)  # we were decrementing the counter, so need to subtract from max val to get elapsed clock cycles
        y = MAXX - (d & 0xFFFF)  # splitting 32-bit number into 2 16-bit numbers
        
        if not last:  # first measurement we are interested in
            last = x + y
            margin = last//20  # tolerate no more than 5% error
            
        delta = (x + y) - last
        
        if abs(delta) < margin:  # measurement is within tolerance
            xtot += x
            ytot += y
            measurements += 1
            last = x + y
            margin = last//20  # tolerate no more than 5% error

    # don't do any expensive maths, just return total clocks for hi and lo
    # and how many samples they represent
    return xtot, ytot, measurements

        
def get_frequency(clk_freq=SM_FREQ):
    
    """Calculate the incoming frequency using the sample from the PIO"""
    
    total = 0
    smp = get_sample()
    print(smp)
    for hi, lo in smp:
        total += hi + lo
    return clk_freq * len(smp) / total / 2

def reset_ema(val):

    """When we change the note, don't want to wait for the ema to catch up, no matter how fast it is. Instead,
    start off with a dummy value which is exactly what we wanted."""

    global EMA
    EMA = val

def get_frequency_ema(min_samples=1):

    """exponential moving average for smoother measurement
    returns the EMA and a flag, True or False, which tells us whether a new sample was included in the calculation"""

    global EMA
    global DUTY_CYCLE  # TODO actually implement

    # need to weight more recent measurements higher

    last = None  # last meaning the one we just looked at, not the final one
    first = True

    if sm_clocker.rx_fifo() < min_samples + 1:  # we asked for a sample but there isn't one yet!
        #  < 2 because we always discard the first sample
        return  EMA, True # just bail and return the same measurement as last time
        # this should be very rare but conceivable if we are measuring very slow waves very quickly
        # the second value is a "stale" flag - if True, we know the measurement didn't change since last time
        # this is important because we don't want the PID integral to wind up while continually measuring the same
        # frequency where in reality the wave cycle just hasn't completed yet

    while sm_clocker.rx_fifo() > 0:
        if first:
            d = sm_clocker.get()  # sadly have to throw away first measurement
            # TODO - if the tuning loop reliably runs at > the maximum audio frequency, then we will never miss
            # a wave cycle, the frequency counter will never stall, and we can use every measurement from it
            first = False
            continue

        d = sm_clocker.get()
        x = MAXX - (d >> 16)
        # we were decrementing the counter, so need to subtract from max val to get elapsed clock cycles
        y = MAXX - (d & 0xFFFF)  # splitting 32-bit number into 2 16-bit numbers

        measurement = x + y  # this func just measures the wave cycle time, we are not interested in hi and lo parts

        if not last:  # first measurement we are interested in
            last = measurement
            margin = last // 20  # tolerate no more than 5% error

        delta = measurement - last

        if abs(delta) < margin:  # measurement is within tolerance
            #  EMA = ALPHA * measurement + (1 - ALPHA) * EMA  # you would use this for alpha = 0.3
            # todo actually - we can be more clever about re-initializing the EMA, just use the first
            # todo measured value for both parts if EMA == 0
            # need to give a few cycles for the freq to stabilize, we are measuring too fast rn!!!
            EMA = ((ALPHA * measurement) >> 12) + (((4096 - ALPHA) * EMA) >> 12)  # fixed point version
            # because it's a FIFO queue, the EMA gives precedence to the newest value we measured
            last = measurement
            margin = last // 20  # tolerate no more than 5% error

    return EMA, False
    
def get_cycle_time(clk_freq=SM_FREQ):
    
    """Return the number of clock cycles (at 125 MHz) that elapsed on average during a full wave cycle"""
    
    total = 0
    smp = get_sample()
    for hi, lo in smp:
        total += hi + lo
    return total // 4  # don't care about fractional clock cycles - 10s of k counts -> 0.01% accuracy with integers
    
    
def freq_to_count(freq, clk_freq=SM_FREQ):
    
    """How many clocks per wave cycle do we expect for this frequency? Work with this number instead of
    Hz frequencies to save on divisions"""
    
    wave_duration = 1.0/freq  # Hz to seconds required for complete cycle
    clocks_per_wave = clk_freq * wave_duration  # the fraction of a second * clocks per second -> clocks per full wave cycle
    
    return int(clocks_per_wave)


def sample_to_frequency(smp):
    hi, lo, counts = smp
    return SM_FREQ * counts / (hi + lo) / 2
    
    
def freq_counter_cleanup():
    
    sm_clocker.active(0)
    sm_edger.active(0)
    print("frequency counter stopped.")


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

def freq_count_reset():

    """Empty the FIFO because we don't want our new measurement contaminated with old values. Most useful when
    we changed frequency and want to only measure the new frequency"""

    while sm_clocker.rx_fifo() > 0:
        sm_clocker.get()
