from array import array
from freq_count_nodma import get_sample_reject_anomalies, longer_sample, sample_to_frequency, freq_count_reset, \
    get_frequency_ema
from line_fitter import Fitter
from mydacs import send_dac_value
import time
from math import log2, floor
from fastlog2 import fast_log2

SM_FREQ = 6_000_000

# lowest note on keyboard = 36
# highest note = 96

A1 = 55.00
NOTES = [0.0] * 33  # unused very low notes
NOTE_WAVECOUNTS = array("I", [0] * 133)
# going from A1 as it's the lowest integer number
# 96 is the highest MIDI note on the keyboard
for x in range(97):
    freq = round(A1 * 2**(x/12.0),2)
    NOTES.append(freq)  # TODO: this is for diagnostic purposes but not control purposes
    NOTE_WAVECOUNTS[x + 33] = fast_log2(int(SM_FREQ//freq//2))  # TODO - can we clean this maths up?
    # generates a list where the item at the index of a MIDI note is the
    # wavecount of that note, that is, how many PIO clock cycles does it take to complete a high + low wave segment
    # so about 54000 for the lowest note, and 180 for the highest - the PIO frequency is chosen so that we use
    # most of the range of a 16-bit counter across the entire range of notes
    # this wavecounts table is used to define the set point of the autotuning PID.


class PidController:

    def __init__(self, p=512, i=320, d=20, setpoint=0):

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

        delta = process_variable - self.setpoint
        time_step = time.ticks_diff(time.ticks_us(), self.last_called)

        slope = ((delta - self.last_error) << 16) // time_step  # for calculating d-term
        # bit shift by 16 because the error needs to be much bigger than the time step
        self.last_error = delta
        self.accumulated_error += delta * time_step
        self.instantaneous_error = delta

        # print("delta: ", delta)

        pterm = (delta * self.p >> 12)
        dterm = (slope * self.d >> 24)
        iterm = (self.accumulated_error * self.i >> 24)

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

class PidController_old:

    # TODO - the PID has no concept of time! So the I term needed will vary depending on how often this is called!

    def __init__(self):
        self.accumulated_error = 0
        self.p = 2  # note these are bit shifts, so 3 means divide by 8
        self.d = 3
        self.i = 4
        self.instantaneous_error = 0

    def reset(self):
        self.accumulated_error = 0
        self.instantaneous_error = 0

    def get_correction(self, note):
        # print("accu error: ", self.accumulated_error)
        hi, lo, count = get_sample_reject_anomalies(min_samples=3)  # returns 2 wave cycles and how many measuemntes
        measured = (hi + lo) // count
        desired = NOTE_WAVECOUNTS[note]
        delta = desired - measured
        self.accumulated_error += delta
        self.instantaneous_error = delta

        correction = (delta >> self.p) + (self.accumulated_error >> self.i) - (delta >> self.d)
        # print("P",delta >> self.p)
        # print("D",delta >> self.d)
        # print("I",self.accumulated_error >> self.i)
        # print(f"Measured: {measured} desired: {desired} delta: {delta} correxion: {correction}")

        return correction  # so hard to keep track of signs

    def get_error(self):
        return self.instantaneous_error

class Oscillator:

    offset = 33  # the lowest MIDI note we can get from the keyboard

    def __init__(self, coarse_index=4, fine_index=5):

        self.c = coarse_index
        self.f = fine_index

        self.coarse_array = array("I", [0] * 150)  # TODO - how long actually?
        self.fine_array = array("I", [0] * 150)

        self.fitter = Fitter()  # mathematical tuning curve before PID fine-tuning
        self.pid = PidController()

        self.target_note = 0  # the number of the MIDI note we have been asked to play. Need to store this to
        # get continuous corrections

    def setup(self, retune=False):

        if retune:
            self.make_tuning_curve()
            self.build_tuning_arrays()
        else:
            self.load_arrays()

    def load_arrays(self):

        try:
            with open("tuning", "rb") as f:
                cnt = 0
                array_size = 150
                dest = self.coarse_array
                while b := f.read(2):
                    v = int.from_bytes(b, "big")
                    dest[cnt] = v
                    cnt += 1
                    if cnt >= array_size:
                        dest = self.fine_array
                        cnt = 0

            print("loaded in tuning arrays")

        except Exception as e:
            print(e)
            print("couldn't find tuning array files, rebuilding them")
            self.setup(retune=True)

    def save_arrays(self):

        with open("tuning", "wb") as f:
            for q in self.coarse_array:
                f.write(q.to_bytes(2, "big"))
            for q in self.fine_array:
                f.write(q.to_bytes(2, "big"))

        print("wrote tuning arrays")

    def make_tuning_curve(self):

        """Use coarse DAC only to establish V:F relationship and use that to make guesses for the fine tuning"""

        send_dac_value(self.f, 127)
        # do initial tuning with half fine adjustment so that we always have "wiggle room"
        # for the fine tuning

        for q in (32, 96, 150, 200, 220):  # using some arbitrary voltages to cover the whole range
            send_dac_value(self.c, q)
            time.sleep(0.01)
            get_sample_reject_anomalies()  # throw away stale data
            time.sleep(0.2)
            r = get_sample_reject_anomalies()
            self.fitter.add(q, log2(sample_to_frequency(r)))

        self.fitter.fit_line()
        print("fitted initial line")

    def note_to_dac_signals(self, note):

        want = NOTES[note]
        dacsignal = self.fitter.getx(log2(want))
        # print(f"want {dacsignal} for {want}")
        cors = round(dacsignal)

        return cors  # 8-bit value to send to the coarse DAC, to which we will add a fine correction

    def correct_old(self):

        """
        Run with the assumption that this oscillator is being monitored by the frequency counter.
        - Read the frequency from the counter
        - compare with what we are supposed to be outputting based on the MIDI note
        - get a correction from our PID loop
        - update the tuning array with the new value
        """

        corr = self.pid.get_correction(self.target_note)
        fine = 127 + corr
        #print("pid correction:", corr)
        if fine < 0:
            return -1, 255
        elif fine > 255:
            return 1, 0
        else:
            return 0, fine



    def build_tuning_arrays(self):

        """Step through all MIDI notes and establish coarse and fine DAC values to send, and store them"""

        note_index = 33
        error_tolerance = 4  # "units" of log2(wavecount) error that we are willing to tolerate
        # 6 units corresponds to 1%

        while note_index < 97:
            print("starting PID tuning...")
            self.pid.setpoint = NOTE_WAVECOUNTS[note_index]
            self.pid.reset()
            corxn = 1000
            error = 100
            corxn = 0
            last_measurement = 0  # if we are tuning very low frequency notes, we might loop several times between
            # audio wave transitions. Need to ignore multiple identical measurements because the system just hasn't
            # had time to respond to the PID signal yet.

            coarse = self.note_to_dac_signals(note_index)  # uses line fit and floats

            print(f"for note {note_index} sending {coarse} to dac")
            print("step\terror\tcorrection")

            send_dac_value(self.c, coarse)
            send_dac_value(self.f, 127)  # start by centering fine
            inc = 0
            err = 999  # arbitrary to start loop
            corrected = False
            while abs(err) > error_tolerance:

                if not corrected:
                    # print(f"tuning note {note_index}")
                    if corxn > 255:
                        coarse += 1
                        send_dac_value(self.c, coarse)
                        send_dac_value(self.f, 127)
                        # just re-centre fine to put us the furthest distance away from another coarse jump
                    elif corxn < 0:
                        coarse -= 1
                        send_dac_value(self.c, coarse)
                        send_dac_value(self.f, 127)
                    else:
                        send_dac_value(self.f, corxn)

                    corrected = True

                #freq_count_reset()  # flush old values from frequency counter FIFO
                #hi, lo, count = get_sample_reject_anomalies(min_samples=4)
                #measured = (hi + lo) // count  # measurement of the actual wavecycle time
                measured, stale = get_frequency_ema()
                if stale:
                    time.sleep(0.0001)
                    continue

                corrected = False
                log_measured = fast_log2(measured)

                #print("measured log wavecycle: ", log_measured)
                #print("target log wavecycle: ", NOTE_WAVECOUNTS[note_index])


                # time.sleep(0.2)
                corxn = self.pid.get_correction(log_measured)
                err = self.pid.get_error()
                tnow = time.ticks_us()
                # print(f"calculated correction: {corxn}")
                print(f"{tnow}\t{err}\t{corxn}")
                inc += 1

            self.coarse_array[note_index] = coarse
            self.fine_array[note_index] = corxn

            # time.sleep(1)

            inc = 0
            print(f"converged for note {note_index}")
            note_index += 1
            self.pid.reset()

        print("fine tuning complete.")


    def play_note(self, midinote):

        c = self.coarse_array[midinote]
        f = self.fine_array[midinote]
        self.target_note = midinote
        self.pid.reset()

        return c, f

        #send_dac_value(self.c, c)
        #send_dac_value(self.f, f)
