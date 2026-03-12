# this module is intended to run in a faster loop on the second core. It monitors for modulation changes and puts
# the instructions in the PIO FIFO to be sent over SPI.

from mydacs import send_dac_value, ADDRESS_MANAGER
from array import array

class DacManager:

    def __init__(self, modulation_array, active_voices):

        self.modulation_array = modulation_array
        self.active_voices = active_voices
        self.modulation_array_copy = array("B", [0] * 48)  # use this to track what we last sent, and only
        # do a DAC transmission if the value changed


    def update(self):

        av = self.active_voices  # make a copy seeing as we are going to destroy it by iterating through the bits
        index = 0
        while av:
            if av & 1:
                self.update_voice(index)
            av >>= 1
            index += 1

    def update_voice(self, index):

        ADDRESS_MANAGER.put(index)  # write voice index to the 3-to-8 decoder, this is the DAC we are updating
        base = index * 8  # index offset in modulation array
        for i in range(8):
            addr = base + i
            new = self.modulation_array[addr]
            if new == self.modulation_array_copy[addr]:
                continue
            self.modulation_array_copy[addr] = new
            send_dac_value(i, new)
