from lcd1602 import LCD
from readmidi import MidiReader
from machine import Pin, I2C
import time
from LFO import LFO
i2c = I2C(0, scl=Pin(17), sda=Pin(16))  # for driving the LCD display
DISPLAY = LCD(i2c)  # set up the text display

MR = MidiReader()

class DummyDisplay:

    def __init__(self):

        self.line1 = [" "] * 16
        self.line2 = [" "] * 16

    def printout(self):

        return f"{"".join(self.line1)}\n{"".join(self.line2)}"

    def update(self, diff1, diff2):

        self.update_line(self.line1, diff1)
        self.update_line(self.line2, diff2)

    def update_line(self, line, diff):

        for start, run in diff:
            ind = start
            for letter in run:
                #print(f"Writing{letter} at index {ind}")
                line[ind] = letter
                ind += 1



import ADSR2, LFO2
from controls import Controls, DisplayManager


adsrlist = [ADSR2.ADSR(), ADSR2.ADSR(),ADSR2.ADSR(),ADSR2.ADSR(),ADSR2.ADSR()]
lfolist = [LFO2.LFO(), LFO2.LFO(), LFO2.LFO(), LFO2.LFO()]
voicelist = [LFO2.LFO()]

C = Controls(voicelist, lfolist, adsrlist)
DM = DisplayManager(voicelist, lfolist, adsrlist)
DD = DummyDisplay()

try: # main loop!
    while 1:

        #time.sleep(0.00001)
        DISPLAY.draw_screen()
        MR.read()  # induce the MidiReader to compile messages to read out
        notes_queue = MR.get_messages("notes")
        controls_queue = MR.get_messages("controls")
        #notes_queue.extend(Y.get(time.ticks_us()))  # testing with hardcoded note seq
        if len(notes_queue) > 1:
            print(notes_queue)
        # this could be lower priority
        if controls_queue:
            for msg in controls_queue:
                C.process_control_signal(*msg)
                ret = C.get_updated()  # todo - careful we aren't discarding things
                if not ret:
                    continue
                ob, parm, value = ret[0]
                if parm:
                    #ob.__setattr__(parm, value)  # not this!!
                    setattr(ob, parm, value)  # but this!!
                pair = DM.update(ret[0])
                #print(outa, outb)
                #DD.update(outa, outb)
                #print(DD.printout())
                #print(pair)
                DISPLAY.update(pair)

                


finally:
    pass


