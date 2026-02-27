from wavetables import EXPO, SAW, RAMP, TRI, SINE, SHARK
from myutils import listindex, fpmult

try:
    from time import ticks_us, ticks_diff

except ImportError:  # for prototyping on desktop when we don't have micropython time module

    import time

    TS = time.time()


    def ticks_us():

        """for testing - microseconds since we started"""

        return int((time.time() - TS) * 1E6)


    def ticks_diff(a, b):

        """So it looks like the time library we are using"""

        return a - b


class LFO:

    def __init__(self):

        """set up references to all of the various function lookup tables"""

        #  TODO: modulatable depth and rate

        self.saw = SAW
        self.ramp = RAMP
        self.tri = TRI
        self.sine = SINE
        self.shark = SHARK

        self.shapenames = ["SAW", "RAMP", "TRIANGLE", "SINE", "SHARKFIN"]
        self.shape_name = "SAW"  # for pretty printing
        self.raw_shape_index = 0  # need the number too for serializing/deserializing

        self.shapes = [self.saw, self.ramp, self.tri, self.sine, self.shark]  # so we can refer to them by index
        self._shape = self.saw  # default
        self.array_length = len(self._shape)  # NOTE - assumes all wavetables have the same resolution

        self._rate = 32768  # default value - internally we use 16 bit rather than 8 for finer grained resolution
        self.set_divisor()

        self._depth = 65535 # default to maximum modulation

        self.last = ticks_us()  # what was the last time we got a value? use this to determine how far to progress the array index
        self.current_index = 0  # record the level we sent last so we can smoothly change parameters without causing a stutter in the output

    def export(self):

        # TODO: can we have a generic export/import method in a super class?

        out = []
        out.append(self.rate)
        out.append(self.depth)
        out.append(self.raw_shape_index)

        return out

    def load(self, ls):

        self.rate = ls[0]
        self.depth = ls[1]
        self.shape = ls[2]

    @property
    def depth(self):

        return self._depth >> 8

    @depth.setter
    def depth(self, new):

        self._depth = new << 8

    @property
    def rate(self):

        return self._rate >> 8

    @rate.setter
    def rate(self, new_value):

        self._rate = new_value << 8
        self.set_divisor()  # calculate the new divisor to get the array index

    @property
    def shape(self):

        return self.shape_name  # we shouldn't need to access the actual shape array directly so just return the name

    @shape.setter
    def shape(self, new_value):

        """Expects a value from 0 to 255 which is mapped to the list of possible shapes"""

        self._shape = listindex(self.shapes, new_value)
        self.shape_name = listindex(self.shapenames, new_value)  # for printing and querying
        self.raw_shape_index = new_value  # for saving/loading


    def set_divisor(self):

        """Given a value from 0-255 corresponding to 10 Hz to 0.1 Hz, calculate how many microseconds between positions in the array.
        """

        #print("frate", self._rate)
        #print("arrlen", self.array_length)
        interval = ((65536 - self._rate) / 65535.0 * 1E7) / self.array_length
        #print("in set divosor method, this is the inverval:", interval)
        # dividing up to 10 seconds across the array indices
        self.divisor = int(interval)

    def get(self, caller=None):

        """caller is optional and allows us to specify a unique phase offset depending on who is asking for an LFO value"""

        # TODO: phase offset

        timenow = ticks_us()
        tdelta = ticks_diff(timenow, self.last)
        index_increment = tdelta // self.divisor
        if index_increment > 0:
            self.last = timenow
        else:
            pass  # if the interval was so fast that we didn't increment the index, we need to NOT store the new
        # time point. Otherwise the tdelta will always be smaller than the step size and we'll never increment the pointer!

        # todo - are these lookups/property accesses slow?
        self.current_index += index_increment
        if self.current_index >= self.array_length:
            self.current_index = self.current_index % self.array_length  # wrap around and deal with the fact that we
            # might have wrapped multiple times (use modulo rather than just subtract array size)

        base_value = self._shape[self.current_index]
        scaled = fpmult(base_value, self._depth)
        #print("from LFO")
        #print(scaled)
        #print(self.current_index)
        return scaled

    def pretty_print(self):

        depth_pct = int(self._depth / 65535.0 * 100)
        line1 = "LFO %i (" + self.shape + ")"
        line2 = "R:%i D:%i%%" % (self.rate, depth_pct)

        return line1, line2
