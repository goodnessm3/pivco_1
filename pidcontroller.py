import time

class PidController:

    def __init__(self, p, i, d, setpoint=0):

        self.accumulated_error = 0
        # p, i, d in the range of 0..4096 and determined experimentally, maybe one day we can have a
        # "PID tuning mode" that lets the user tweak the values
        self.p = p
        self.d = d
        self.i = i
        self.setpoint = setpoint
        self.instantaneous_error = 0  # for diagnostic purposes
        self.last_called = time.ticks_us()  # the microsecond timestamp when we last asked for a correction
        self.last_error = 0

    def reset(self):

        self.accumulated_error = 0
        self.instantaneous_error = 0
        self.last_called = time.ticks_us()

    def get_correction(self, process_variable):

        #  TODO - derivative term based on change in PV not ERROR 21/03

        tnow = time.ticks_us()

        delta = process_variable - self.setpoint
        time_step = time.ticks_diff(tnow, self.last_called)
        self.last_called = tnow

        slope = ((delta - self.last_error) << 16) // time_step  # for calculating d-term
        # bit shift by 16 because the error needs to be much bigger than the time step
        self.last_error = delta
        self.accumulated_error += delta * time_step
        self.instantaneous_error = delta

        # print("delta: ", delta)

        pterm = (delta * self.p >> 14)
        dterm = (slope * self.d >> 26)
        iterm = (self.accumulated_error * self.i >> 26)

        # correction = (delta >> self.p) + (self.accumulated_error >> self.i) - (delta >> self.d)
        correction = pterm - dterm + iterm
        # print("P-term: ", pterm)
        # print("I-term: ", iterm)
        # print("D-term: ", dterm)
        # print("correction: ", correction)
        # print("---")

        return correction

    def get_error(self):
        return self.instantaneous_error