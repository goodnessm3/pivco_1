import machine
from machine import Pin

spi = machine.SPI(0,
                  baudrate=1000000,
                  polarity=0,
                  phase=0,
                  bits=8,
                  firstbit=machine.SPI.MSB,
                  sck=machine.Pin(18),
                  mosi=machine.Pin(19),
                  miso=machine.Pin(16))

def write_to_dac(b):

    """Expects a 16-bit command that will be split into two bytes for sending"""

    bs = b.to_bytes(2, "big")
    #print(bytes_to_binary_string(bs))
    #CS_PIN.low()  # note - CS is now really AEN of the 74HC138, so active high -> actual CS pin goes low
    #time.sleep(0.001)
    spi.write(bs)
    #time.sleep(0.001)
    #CS_PIN.high()
    #time.sleep(0.001)

import time

while 1:
    time.sleep(1)
    write_to_dac(0b0000001111111111)