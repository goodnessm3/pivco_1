import machine
from machine import Pin
import time
from math import floor

CS_PIN = Pin(21,Pin.OUT,Pin.PULL_UP)  # this is really address enable on the PCB test
RST_PIN = Pin(22,Pin.OUT,Pin.PULL_UP)
RST_PIN.low()
CS_PIN.low()  # address enable is active HIGH
TUNE_LATCH_PIN = Pin(26,Pin.OUT,value=1)

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

    """Expects a 16-bit command that will be split into two bytes for sending"""

    bs = b.to_bytes(2, "big")
    #print(bytes_to_binary_string(bs))
    CS_PIN.low()  # note - CS is now really AEN of the 74HC138, so active high -> actual CS pin goes low
    #time.sleep(0.001)
    spi.write(bs)
    #time.sleep(0.001)
    CS_PIN.high()
    #time.sleep(0.001)


def send_dac_value(dac, val):

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