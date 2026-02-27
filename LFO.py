# LFO wave tables are pre-computed so that one cycle takes 100 ms (10 Hz maximum LFO rate)
# 1000 data points per cycle

def saw():
    # just a wave form that ramps up and then resets

    out = []

    for x in range(1000):
        out.append(int(x * 0.001 * 127))

    return out


def ramp():
    return list([127 - x for x in saw()])


# set up wave tables for LFO functions
SAW = saw()
RAMP = ramp()
TRIANGLE = SAW[::2] + RAMP[::2]

REF = {"saw":SAW, "ramp":RAMP, "triangle":TRIANGLE}

class LFO:

    def __init__(self, rate_ref):
        # TODO: get away from floats!?!??!?!

        self.shape = SAW
        self.divisor = 1  # what to divide the list index by. When there is no division, rate = 10 Hz because the table describes 100 ms of wave
        self.cycle_time = 1E5  # how many microseconds does it take to go thru a full cycle
        self.rate = rate_ref  # points to a parameter under control of a physical slider

    def set_rate(self, rate):
        """compute the internal divisor required for a specified rate in Hz"""

        self.divisor = 10.0 / rate  # 10 Hz = divisor is 1, 0.1 Hz (100 x slower) - divisor is 100
        self.cycle_time = int(1E6 / rate)

    def set_shape(self, shape):
        """shape is a reference to a list of points describing a full wave cycle taking 100 ms"""

        self.shape = REF[shape]

    def control_to_hz(self, ctl):

        """Map a control value of 0 to 127 to a Hz frequency in a useful range (10 Hz to 0.1 Hz)
        Low slider = slow LFO"""

        return 10 ** (ctl / 127.0 * 2 - 1)

    def get(self, time_point):
        """time_point is microseconds since instantiation. Take the modulo with the cycle time to find out how far thru the cycle we are."""

        # 1000 data points describe points from 0 to 100,000 microseconds. So there's an extra factor of 100 in there.

        #print(self.rate)
        #print(type(self.rate))
        desired_rate = self.control_to_hz(self.rate.get())  # todo: cleanup

        self.divisor = 10.0 / desired_rate  # 10 Hz = divisor is 1, 0.1 Hz (100 x slower) - divisor is 100
        self.cycle_time = int(1E6 / desired_rate)

        t = time_point % self.cycle_time
        t = t / self.divisor / 100.0  # extra factor as above
        t = int(t)

        #print(f"t: {t} index: {self.index}")

        return self.shape[t]