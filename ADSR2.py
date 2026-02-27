
from wavetables import EXPO
from myutils import fpmult

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


class ADSR:

    def __init__(self):

        """Minimum interesting phase time = 10 ms, maximum = 10 s (3 orders of magnitude)
        This object expects parameters in the range of 0..255 so 255 = a 10s attack, decay or release
        function is (blah/255) * 3 + 4  -> maps an input of 0..255 to a range from 4 to 7, which is orders of mag of
        microseconds then need to spread the lookup table across that whole range. How do I even explain this.
        """

        self.arr = EXPO  # our reference to the global expo array
        self.array_length = len(self.arr)

        self._a = 127  # sensible defaults halfway thru range
        self.a_d = self.get_divisor(self._a)
        self._d = 127
        self.d_d = self.get_divisor(self._d)
        self._s = 32768
        self._r = 127
        self.r_d = self.get_divisor(self._r)

        self._depth = 65535

        self.gate_starts = {}  # a dictionary of caller: start time in microseconds
        self.gate_status = {}  # caller: True/False - gate signal. True = gate is open
        self.level = 0  # current output, 0-32767
        self.sustaining = False
        self.decaying = False
        self.attacking = False
        self.releasing = False
        self.releasing_from = None  # we can't always assume we are releasing from the sustain level if note was
        # released during decay phase
        self.attack_fastforward = 0  # array offset if we want to start attacking from a higher base level

    def export(self):

        return [self.a, self.d, self.s, self.r, self.depth]

    def load(self, ls):

        self.a = ls[0]
        self.d = ls[1]
        self.s = ls[2]
        self.r = ls[3]
        self.depth = ls[4]


    def get_fastforward(self):

        ind = -1
        l = 0
        arrlength = len(self.arr)
        while l < self.level and ind < arrlength - 1:
            ind += 1
            l = 65535 - self.arr[ind]
        return ind

    @property
    def a(self):

        return self._a

    @a.setter
    def a(self, new_value):

        self._a = new_value
        self.a_d = self.get_divisor(self._a)

    @property
    def d(self):

        return self._d

    @d.setter
    def d(self, new_value):

        self._d = new_value
        self.d_d = self.get_divisor(self._d)

    @property
    def r(self):

        return self._r

    @r.setter
    def r(self, new_value):

        self._r = new_value
        self.r_d = self.get_divisor(self._r)

    @property
    def s(self):

        """S is set by a hardware slider, but internally we need to make it the same magnitude as the table values"""

        return self._s >> 8

    @s.setter
    def s(self, new_value):

        self._s = new_value << 8

    @property
    def depth(self):

        return self._depth >> 8

    @depth.setter
    def depth(self, new):

        self._depth = new << 8


    def gate(self, caller, status):

        """As far as caller is concerned, the ADSR has been running since the start of the gate function. Status = True either starts or restarts
        the envelope from the beginning of the attack phase. As long as gate is open we will hold at the sustain value after going thru attack
        and decay phases. When status=False, the decay phase commences."""

        self.gate_starts[caller] = ticks_us()
        self.gate_status[caller] = status

        # if we recieved gate on or off, then we aren't in either of these states:
        self.decaying = False
        self.sustaining = False
        self.releasing_from = self.level  # store the level to use for vertically scaling the next phase

        if status:
            self.attacking = True
            self.releasing = False
            self.attack_fastforward = self.get_fastforward()
        else:
            self.attacking = False
            self.releasing = True

    def get_divisor(self, rate):

        """Given a value from 0-255 corresponding to 1ms to 10s, calculate how many microseconds between positions in the array.
        For the default 100 point array to be covered in 2 seconds, each increment is 20,000 us"""

        length = 10 ** ((rate / 255.0) * 3 + 4)  # map 0-255 to 10 - 10,000 ms
        interval = length / (
                    len(self.arr) / 2)  # table covers 2 "intervals" - 100 points for a 2-second sample so 50 points per second

        return int(interval)

    def pretty_print(self):

        depth_pct = int(self._depth/65535.0 * 100)
        line1 = "ADSR %i " + "(" + str(depth_pct) + "%%" + ")"
        line2 = "%i %i %i %i" % (self.a, self.d, self.s, self.r)

        return line1, line2

    def get(self, caller):

        retval = self.old_get(caller)
        return fpmult(retval, self._depth)

    def old_get(self, caller):

        """return the current magnitude of the envelope signal. We add timedelta to the
        start of the gate signal to determine how far thru the cycle we are."""

        # TODO: linear interpolation between coarser table values
        # TODO: probably just a single return point so we can apply the depth scaling nicely

        if self.sustaining:
            return self.level  # TODO: accurately decay to sustain level so pitch mod is in-tune

        try:
            tdelta = ticks_diff(ticks_us(), self.gate_starts[caller])
        except KeyError:  # at the very start, we will be trying to update this having never gated it
            self.gate_starts[caller] = 0  # effectively some time arbitrarily far in the past

        try:
            stat = self.gate_status[caller]
        except KeyError:
            self.gate_status[caller] = False  # as above
            stat = False

        if stat:
            # gate is true but we didn't reach the sustain level, must be attacking or decaying
            if self.attacking:
                index = tdelta // self.a_d + self.attack_fastforward

                # we need to "fast-forward" thru the attack array if we are coming from some residual decay/release level

                # print(ticks_us(), self.gate_starts[caller])
                # print(self.a_d)
                # print("atack and index is", index)
                if index < self.array_length and self.level < 65535:
                    # within attack phase
                    lev = 65535 - self.arr[index]  # exponential INCREASE, so 1 minus
                    # add the level if we are re-initiating an attack during the decay phase
                    self.level = lev
                    return min(lev, 65535)
                    # this is the only place we could go over 255 because of adding the previous level. Never want this.
                    # level >= 255 will be detected in the next "get" call and push us into the decay phase.
                else:  # finished the attack array and now it is time to decay
                    self.attacking = False
                    self.decaying = True
                    self.gate_starts[caller] = ticks_us()  # reset time counter for decay curve now
                    lev = 65535 - self.arr[-1]
                    self.level = lev
                    self.releasing_from = lev  # record how high we got and use it to scale the decay phase
                    return lev
            else:
                # we must be decaying, sustain was handled further up
                index = tdelta // self.d_d
                if index < self.array_length:
                    decay_point = self.arr[index]  # those arrays follow each other
                    # we need to vertically scale the decay to squash it into the space between max level and sustain level
                    # then add the "floor" of the sustain level
                    scalerange = self.releasing_from - self._s
                    lev = self._s + fpmult(decay_point, scalerange)
                    # lev = self.level - fpmult(decay_point, (self.releasing_from << 1))

                    self.level = lev
                    return lev
                else:  # we reached the end of the decay table so now just hold at the sustain level
                    self.decaying = False
                    self.sustaining = True
                    return self.level  # always need to return something so start sustaining
                    # note that we never actually reach the value specified by the sustain parameter because the expo function can never reach it
                    # we will always be just a little over, but this avoids a discontinuity when exiting the decay function
        else:  # release phase
            if self.releasing:
                index = tdelta // self.r_d
                if index < self.array_length:
                    release_point = self.arr[index]
                    lev = fpmult(release_point,
                                 self.releasing_from)  # need to vertically squash release values to decrease from the current level
                    # releasing_from was set when the gate signal went False
                    self.level = lev
                    return lev
                else:
                    self.releasing = False
                    return 0  # we ran past the end of the release table, envelope has completed.
            else:
                return 0  # not sustaining, not gated, not releasing, nothing is happening