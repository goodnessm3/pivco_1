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
PIN_IN = 9
PIN_SYNC = 11
SM_FREQ = 6_000_000
MAXX = 2**16-1


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

# CHANGED 2201 - REMOVE WAITS!???
@asm_pio(fifo_join=PIO.JOIN_RX)
def clocker16():  
    mov(x, invert(0x00000000))
    wrap_target()
    label("count")
    jmp(pin, "write")  # Check sync pin
    jmp(x_dec, "count")
    label("write")
    in_(x, 16)        # Capture count with bit shift
    mov(x, invert(0x00000000))        # Reset Counter immediately
    label("count2")
    jmp(pin, "write2")  # Check sync pin
    jmp(x_dec, "count2")
    label("write2")
    in_(x, 16)        # Capture count with bit shift
    push(block)      # Send to FIFO, only send every two cycles
    mov(x, invert(0x00000000))        # Reset Counter immediately
    wrap()
    
    
@asm_pio()
def clocker_orig():
    pull(noblock)      # Load max counter value to OSR
    mov(x, osr)        # Reset Counter
    wrap_target()
    label("count")
    jmp(pin, "write")  # Check sync pin
    jmp(x_dec, "count")
    label("write")
    mov(isr, x)        # Capture count
    push(noblock)      # Send to FIFO
    mov(x, osr)        # Reset Counter immediately
    wait(0, pin, 0)    # Wait for sync low
    wrap()
    
    

# CHANGED DELAY 2 to 1 at 22:29
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
gppin = machine.Pin(PIN_IN, machine.Pin.IN, machine.Pin.PULL_UP)
sidepin = machine.Pin(PIN_SYNC, machine.Pin.OUT)
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
    
    
""" old clocker16 at 22:02

@asm_pio(fifo_join=PIO.JOIN_RX)
def clocker16():  
    mov(x, invert(0x00000000))
    wrap_target()
    label("count")
    jmp(pin, "write")  # Check sync pin
    jmp(x_dec, "count")
    label("write")
    in_(x, 16)        # Capture count with bit shift
    mov(x, invert(0x00000000))        # Reset Counter immediately
    wait(0, pin, 0)    # Wait for sync low
    label("count2")
    jmp(pin, "write2")  # Check sync pin
    jmp(x_dec, "count2")
    label("write2")
    in_(x, 16)        # Capture count with bit shift
    push(block)      # Send to FIFO, only send every two cycles
    mov(x, invert(0x00000000))        # Reset Counter immediately
    wait(1, pin, 0)    # Wait for sync high  # CHANGED 2200 - high not low
    wrap()
    
"""