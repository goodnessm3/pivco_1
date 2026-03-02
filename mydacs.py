import machine
from machine import Pin
import time
from math import floor
import rp2
from rp2 import PIO, asm_pio

#CS_PIN = Pin(21,Pin.OUT,Pin.PULL_UP)  # this is really address enable on the PCB test
RST_PIN = Pin(8,Pin.OUT,Pin.PULL_UP)
RST_PIN.low()
#CS_PIN.low()  # address enable is active HIGH
TUNE_LATCH_PIN = Pin(4,Pin.OUT,value=1)

"""
spi = machine.SPI(0,
                  baudrate=1000000,
                  polarity=0,
                  phase=0,
                  bits=8,
                  firstbit=machine.SPI.MSB,
                  sck=machine.Pin(18),
                  mosi=machine.Pin(19),
                  miso=machine.Pin(16))

"""

"""
# temporary - set up tune latch on startup
time.sleep(1)
CS_PIN.high()  # logical high +12 V on CS
time.sleep(1)
TUNE_LATCH_PIN.low()  # rising edge of clock pin
time.sleep(1)
TUNE_LATCH_PIN.high()  # falling edge of clock, data is latched
time.sleep(1)
CS_PIN.low()  # data goes low but we saved the bit
"""

# custom SPI that manages CS transitions between 12-bit instructions
@asm_pio(
    out_init=PIO.OUT_LOW,
    set_init=PIO.OUT_LOW,
    sideset_init=PIO.OUT_LOW, #!!!!
    out_shiftdir=PIO.SHIFT_LEFT,
    autopull=False,
    pull_thresh=12,
)
def myspi():  # TODO: packing to put multiple instructions per word
    pull(block)  # wait here to load 32-bit value from RX FIFO
    #set(x, 1)  # two instructions are packed into a 32-bit word
    #label("outer")
    set(pins, 1)  # enable high -> CS low -> DAC starts listening
    set(y,11)  # counter for sending 12-bit DAC instruction
    label("bitloop")
    out(pins, 1).side(0) # put the data on MOSI pin and bring clock low
    nop().side(1)  # rising edge of clock so bit is read into DAC
    jmp(y_dec, "bitloop")  # repeat until we've written 12 bits of data
    set(pins, 0)  # enable low -> CS high -> data is latched in
    #jmp(x_dec, "outer")  # loop back to send the second instruction

# address line manager, writes the binary address (0-7) to the output pins
@asm_pio(
    out_init=(PIO.OUT_LOW,) *3,
    out_shiftdir=PIO.SHIFT_RIGHT,
    autopull=True,
    pull_thresh=3,
)
def addressmgr():
    out(pins, 3)


MOSI_PIN = 16
AEN_PIN = 18
SCK_PIN = 17
ADDRESS_BASE_PIN = 19  # this and the next 2 pins are used for A0, A1 and A2 for the 3-to-8


sm_spi = rp2.StateMachine(2, myspi, freq=1000000, out_base=Pin(MOSI_PIN),
    set_base=Pin(AEN_PIN),
    sideset_base=Pin(SCK_PIN))
sm_spi.active(1)

# 19, 20, 21 address pins
# this state machine is accessed from within the main program loop
ADDRESS_MANAGER = rp2.StateMachine(3, addressmgr, freq=1000000, out_base=Pin(ADDRESS_BASE_PIN))
ADDRESS_MANAGER.active(1)

#admgr.put(0)  # TODO - this is temporary, we eventually need to manage addresses of multiple DACs

def bytes_to_binary_string(bytes_data):
    """
    Converts a bytes object into a string representing its binary value.

    Args:
        bytes_data: A bytes object.

    Returns:
        A string representing the binary value of the bytes object.
    """
    binary_parts = []
    for byte in bytes_data:
        # Format each byte as an 8-bit binary string, zero-padded
        binary_parts.append(f"{byte:08b}")
    return "".join(binary_parts)


def make_dac_bytes(val, channel):

    """Ask the DAC to output a fraction (0-255) of its total voltage
    on channel 1 thru 8"""
    
    if type(val) is not int:
        raise ValueError("DAC expects an 8-bit value")
    
    chans = [0b1000,
             0b0100,
             0b1100,
             0b0010,
             0b1010,
             0b0110,
             0b1110,
             0b0001
        ]  # can't just use the channel number directly
    # because teh DAC expects it BACKWARDS.

    #amt = int(frac * 255.0)  # 8-bit DAC so work out the fraction of 255

    word = (chans[channel] << 8) | val

    return word


def dac_setup():
    
    time.sleep(1)  # DACs should be reset once power has stabilized
    RST_PIN.high()

    msg1 = 0b0000100100000000  # power down release
    msg2 = 0b0000001111111111  # all channels to analog output (I/O DA select)
    msg3 = 0b0000111111111111  # all channels to output mode (I/O status setting)

    write_to_dac(msg1)
    write_to_dac(msg2)
    write_to_dac(msg3)

    print("dac setup done")

def write_to_dac(b):

    sm_spi.put(b << 20)  # TODO: this currently only handles a single instruction

def write_to_dac_old(b):

    """Expects a 16-bit command that will be split into two bytes for sending"""

    bs = b.to_bytes(2, "big")
    #print(bytes_to_binary_string(bs))
    CS_PIN.low()
    #time.sleep(0.001)
    spi.write(bs)
    #time.sleep(0.001)
    CS_PIN.high()
    #time.sleep(0.001)


def send_dac_value(dac, val):

    #print("sending val ", val, "to ", dac)

    if val < 0:
        print(f"warning - {val} was clamped to 0")
        val = 0
        
    if val > 255:
        print(f"warning - {val} was clamped to 255")
        val = 255

    msg = make_dac_bytes(val, dac)  # send val (0 to 255) to dac channel number
    write_to_dac(msg)

def send_dac_fraction(dac, val):

    """Set the dac with a float between 0.0 and 1.0, we translate it here to 8-bit"""

    v = floor(val * 255)
    send_dac_value(dac, v)