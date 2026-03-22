import time
from array import array

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
        self.last_sent = 0  # compute the D-term on the control signal, not the error
        self.resetted = False  # for the first iteration after a setpoint change, send the last value we optimized to

        self.accumulated_error_array = array("i", [0] * 97)
        self.correction_signal_array = array("i", [0] * 97)
        self.current_note = 0  # need this to know where to stash the current accu error when the setpoint changes

    def reset(self, midinote=None):

        if midinote:
            self.accumulated_error_array[self.current_note] = self.accumulated_error  # store error for this note
            self.correction_signal_array[self.current_note] = self.last_sent  # so we can resume when replay this note
            self.accumulated_error = self.accumulated_error_array[midinote]  # look up value for new note
            self.last_sent = self.correction_signal_array[midinote]
            # PID needs to remember the value it established when previously asked to tune this note
            self.current_note = midinote
        else:
            self.accumulated_error = 0

        self.instantaneous_error = 0
        self.last_called = time.ticks_us()
        self.resetted = True

    def get_correction(self, process_variable):

        #  TODO - derivative term based on change in PV not ERROR 21/03

        tnow = time.ticks_us()

        delta = process_variable - self.setpoint
        time_step = time.ticks_diff(tnow, self.last_called)
        self.last_called = tnow

        if self.resetted:
            self.resetted = False
            return self.last_sent
            # this value is written by the reset method and allows us to restart where we left off

        self.last_error = delta
        self.accumulated_error += delta * time_step
        self.instantaneous_error = delta

        # print("delta: ", delta)

        pterm = min((delta * self.p >> 14), 225)  # add clamping
        iterm = (self.accumulated_error * self.i >> 26)

        pi = pterm + iterm
        slope = ((self.last_sent - pi) << 16) // time_step
        # bit shift by 16 because the error needs to be much bigger than the time step
        dterm = (slope * self.d >> 18)  # applying D-term to the correction that we are ABOUT to send

        # correction = (delta >> self.p) + (self.accumulated_error >> self.i) - (delta >> self.d)
        correction = pterm - dterm + iterm
        # print("P-term: ", pterm)
        # print("I-term: ", iterm)
        # print("D-term: ", dterm)
        # print("correction: ", correction)
        # print("---")

        self.last_sent = correction
        return correction

    def get_error(self):
        return self.instantaneous_error