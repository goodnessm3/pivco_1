from array import array
from freq_count_nodma import get_sample_reject_anomalies, longer_sample, sample_to_frequency
from line_fitter import Fitter
from mydacs import send_dac_value
import time
from math import log2, floor

SM_FREQ = 6_000_000

# lowest note on keyboard = 36
# highest note = 96

A1 = 55.00
NOTES = [0.0] * 33  # unused very low notes
NOTE_WAVECOUNTS = array("I", [0] * 150)
# going from A1 as it's the lowest integer number
for x in range(100):
    freq = round(A1 * 2**(x/12.0),2)
    NOTES.append(freq)  # TODO: this is for diagnostic purposes but not control purposes
    NOTE_WAVECOUNTS[x + 33] = (int(SM_FREQ//freq//2))
    # generates a list where the item at the index of a MIDI note is the
    # frequency of that note, or wavecount to avoid divisions

class PidController:

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

        return -1 * correction  # so hard to keep track of signs

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

    def correct(self):

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

        while note_index < 97:
            print("starting PID tuning...")
            corxn = 1000
            error = 100
            corr = 0
            test_note = note_index
            #want = NOTES[note_index]
            coarse = self.note_to_dac_signals(test_note)  # uses line fit and floats

            print(f"for note {note_index} sending {coarse} to dac")
            print("step\terror\tcorrection")

            send_dac_value(self.c, coarse)
            send_dac_value(self.f, 127)  # start by centering fine
            inc = 0
            err = 999  # arbitrary to start loop
            while abs(err) > 15:
                # print(f"tuning note {note_index}")
                if corr > 255:
                    coarse += 1
                    send_dac_value(self.c, coarse)
                    send_dac_value(self.f, 127)
                    # just re-centre fine to put us the furthest distance away from another coarse jump
                elif corr < 0:
                    coarse -= 1
                    send_dac_value(self.c, coarse)
                    send_dac_value(self.f, 127)
                else:
                    send_dac_value(self.f, corr)

                get_sample_reject_anomalies()  # flush old values from frequency counter FIFO
                # time.sleep(0.2)

                # measured_freq = sample_to_frequency(longer_sample())
                # error = (measured_freq - want) / want * 100
                # time.sleep(0.1)
                # print(f"{want}\t{measured_freq}\t{error}%")
                # print("---")
                corxn = self.pid.get_correction(note_index)
                err = self.pid.get_error()
                corr = 127 + corxn
                # print(f"calculated correction: {corxn}")
                print(f"{inc}\t{err}\t{corxn}")
                inc += 1
            self.coarse_array[note_index] = coarse
            self.fine_array[note_index] = corr

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
