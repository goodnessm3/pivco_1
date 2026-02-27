from machine import Pin, I2C
import time


class LCD:
    def __init__(self, i2c, addr=None, backlight_enable=1):
        self.bus = i2c
        self.addr = self.scanAddress(addr)
        self.backlight_enable = backlight_enable
        self.txbuf = bytearray(4)  # don't allocate it every time we write
        self.send_data(0x33, 0)  # Must initialize to 8-line mode at first
        time.sleep(0.005)
        self.send_data(0x32, 0)  # Then initialize to 4-line mode
        time.sleep(0.005)
        self.send_data(0x28, 0)  # 2 Lines & 5*7 dots
        time.sleep(0.005)
        self.send_data(0x0C, 0)  # Enable display without cursor
        time.sleep(0.005)
        self.send_data(0x01, 0)  # Clear Screen
        self.bus.writeto(self.addr, bytearray([0x08]))

    def scanAddress(self, addr):
        devices = self.bus.scan()
        if len(devices) == 0:
            raise Exception("No LCD found")
        if addr is not None:
            if addr in devices:
                return addr
            else:
                raise Exception(f"LCD at 0x{addr:2X} not found")
        elif 0x27 in devices:
            return 0x27
        elif 0x3F in devices:
            return 0x3F
        else:
            raise Exception("No LCD found")

    def write_word(self, data):
        print(data)
        temp = data
        if self.backlight_enable == 1:
            temp |= 0x08
        else:
            temp &= 0xF7
        self.bus.writeto(self.addr, bytearray([temp]))

    def build_instruction_queue(self, ls, line):

        """given a list of update tuples, break it into instructions to be sent to the LCD screen"""
        # only need to position the cursor once, then it auto-increments
        # need to tell it whether it's on line 0 (top) or 1 to set the y address appropriately

        out = []
        for loc, chrs in ls:
            out.append((0x80 + 0x40 * line + loc, 0))  # position cursor and 0 = command, not data
            for c in chrs:
                out.append((ord(c), 1))

        return out





    def send_data(self, data, rs):

        """rs = 1: data, 0: command"""
        RS = 0x01 if rs else 0x00
        BL = 0x08
        EN = 0x04

        high = (data & 0xF0) | RS | BL
        low = ((data << 4) & 0xF0) | RS | BL

        self.txbuf[0] = high | EN
        self.txbuf[1] = high
        self.txbuf[2] = low | EN
        self.txbuf[3] = low

        self.bus.writeto(self.addr, self.txbuf)

        time.sleep_us(40)

    def position_cursor(self, x, y):

        if x < 0:
            x = 0
        if x > 15:
            x = 15
        if y < 0:
            y = 0
        if y > 1:
            y = 1

        # calculate cursor address and send it
        addr = 0x80 + 0x40 * y + x
        self.send_data(addr, 0)


    def clear(self):
        self.send_command(0x01)  # Clear Screen

    def openlight(self):  # Enable the backlight
        self.bus.writeto(self.addr, bytearray([0x08]))
        # self.bus.close()

    def write(self, x, y, str):
        if x < 0:
            x = 0
        if x > 15:
            x = 15
        if y < 0:
            y = 0
        if y > 1:
            y = 1

        # Move cursor
        addr = 0x80 + 0x40 * y + x
        self.send_command(addr)

        for chr in str:
            self.send_data(ord(chr))

    def message(self, text):
        # print("message: %s"%text)
        for char in text:
            if char == "\n":
                self.send_data(0xC0, 0)  # next line
            else:
                self.send_data(ord(char), 1)


    def wordtoarray(self, astr):

        out = bytearray([])
        for q in astr:
            out.append(ord(q))
        return out


    def send_data_old(self, data):
        # Send bit7-4 firstly
        buf = data & 0xF0
        buf |= 0x05  # RS = 1, RW = 0, EN = 1
        self.write_word(buf)
        time.sleep(0.002)
        buf &= 0xFB  # Make EN = 0
        self.write_word(buf)

        # Send bit3-0 secondly
        buf = (data & 0x0F) << 4
        buf |= 0x05  # RS = 1, RW = 0, EN = 1
        self.write_word(buf)
        time.sleep(0.002)
        buf &= 0xFB  # Make EN = 0
        self.write_word(buf)

    def send_command(self, cmd):
        # Send bit7-4 firstly
        buf = cmd & 0xF0
        buf |= 0x04  # RS = 0, RW = 0, EN = 1
        self.write_word(buf)
        time.sleep(0.002)
        buf &= 0xFB  # Make EN = 0
        self.write_word(buf)

        # Send bit3-0 secondly
        buf = (cmd & 0x0F) << 4
        buf |= 0x04  # RS = 0, RW = 0, EN = 1
        self.write_word(buf)
        time.sleep(0.002)
        buf &= 0xFB  # Make EN = 0
        self.write_word(buf)

if __name__ == "__main__":
    i2c = I2C(0, scl=Pin(17), sda=Pin(16))  # for driving the LCD display
    import random
    import time
    letters = [chr(x) for x in range(65, 91)]
    LC = LCD(i2c)

    LC.message("Loading...")
    time.sleep(1)
    while True:
        st = ""
        for q in range(0, 12):
            st += letters[random.randint(0, 25)]
        LC.message(st)
        time.sleep(0.1)
