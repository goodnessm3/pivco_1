


# pins: A0, A1, A2, AEN, sclk, mosi


# changes: RST 22 to 10 to 8
# CS TEST 27 to 7
# tune latch 26 to 4

# decoder pin 6 = enable (Active high)
# pints 1,2,3 = address

# regular SPI is pins 18, 19
# so use 20 - 23 for addressing


# 20 - enable, 21, 22, 26 address

import machine
from machine import Pin
import rp2
from rp2 import PIO, asm_pio

# start w clock low, data is read on every rising edge

@asm_pio(
    out_init=PIO.OUT_LOW,
    set_init=PIO.OUT_LOW,
    sideset_init=PIO.OUT_LOW, #!!!!
    out_shiftdir=PIO.SHIFT_LEFT,
    autopull=False,
    pull_thresh=12,
)
def myspi():
    pull(block)  # wait here to load 32-bit value from RX FIFO
    set(x, 1)  # two instructions are packed into a 32-bit word
    label("outer")
    set(pins, 1)  # enable high -> CS low -> DAC starts listening
    set(y,11)  # counter for sending 12-bit DAC instruction
    label("bitloop")
    out(pins, 1).side(0) # put the data on MOSI pin and bring clock low
    nop().side(1)  # rising edge of clock so bit is read into DAC
    jmp(y_dec, "bitloop")  # repeat until we've written 12 bits of data
    set(pins, 0)  # enable low -> CS high -> data is latched in
    jmp(x_dec, "outer")  # loop back to send the second instruction


@asm_pio(
    out_init=(PIO.OUT_LOW,) *3,
    out_shiftdir=PIO.SHIFT_RIGHT,
    autopull=True,
    pull_thresh=3,
)
def addressmgr():
    out(pins, 3)

MOSI_PIN = 16
ADDR_BASE_PIN = 18
SCK_PIN = 17 #
# swapped data and clock to get contiguous output 17 18 19 20 and now AEN is pin 21


sm_spi = rp2.StateMachine(2, myspi, freq=1000000, out_base=Pin(MOSI_PIN),
    set_base=Pin(ADDR_BASE_PIN),
    sideset_base=Pin(SCK_PIN))
sm_spi.active(1)


# 19, 20, 21 address bits
admgr = rp2.StateMachine(3, addressmgr, freq=1000000, out_base=Pin(19))
admgr.active(1)

# !!! important! All pins of the SPI PIO must be contiguous! Apparently

import time

cnt = 0
start = time.ticks_us()

try:

    while True:

        for x in range(8):
            time.sleep(0.3)
            sm_spi.put(0b001111111111 << 20)
            admgr.put(x)
            print("put", x)
        cnt += 1

finally:
    end = time.ticks_us()
    duration = time.ticks_diff(end, start)
    print(cnt, "cycles in", duration, "us")
    tpc = float(cnt)/duration*1E6
    print(tpc, " cycles per second")



# 53k cycles per second with PIO
# 25k per second with pin.value()