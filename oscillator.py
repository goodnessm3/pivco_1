from array import array
from freq_count_nodma import get_sample_reject_anomalies, longer_sample, sample_to_frequency, freq_count_reset, \
    get_frequency_ema, reset_ema
from line_fitter import Fitter
from mydacs import send_dac_value
import time
from math import log2, floor
from fastlog2 import fast_log2

from wavecount_table import NOTE_WAVECOUNTS, NOTES

SM_FREQ = 6_000_000

# lowest note on keyboard = 36
# highest note = 96

"""  # MOVED to its own module so it can be used elsewhere
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
"""

from pidcontroller import PidController


class Oscillator:

    offset = 33  # the lowest MIDI note we can get from the keyboard

    def __init__(self, addr, coarse_index=4, fine_index=5):

        self.c = coarse_index
        self.f = fine_index
        self.addr = addr  # an oscillator will be associated with a certain voice and needs to keep track of
        # its identity as tuning tables are unique

        self.coarse_array = array("I", [0] * 150)  # TODO - how long actually?
        self.fine_array = array("I", [0] * 150)

        self.fitter = Fitter()  # mathematical tuning curve before PID fine-tuning
        self.pid = PidController(6000, 36, 4096)  # todo - eventually this will be fully decoupled from the oscillator class
        # and managed by the autotuning core instead

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
            with open(f"tuning{self.addr}", "rb") as f:
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

        with open(f"tuning{self.addr}", "wb") as f:
            for q in self.coarse_array:
                f.write(q.to_bytes(2, "big"))
            for q in self.fine_array:
                f.write(q.to_bytes(2, "big"))

        print(f"wrote tuning arrays to tuning{self.addr}")

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

        """only for use in building the initial array, slow!!!"""

        # TODO - just do away with this and use our fast log2 approx instead

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

        # 6 units corresponds to 1%
        error_count_threshold = 4


        while note_index < 97:
            print("starting PID tuning...")
            self.pid.setpoint = NOTE_WAVECOUNTS[note_index]
            self.pid.reset()
            reset_ema(NOTE_WAVECOUNTS[note_index])  # optimistically say we measured what we wanted

            dwc = NOTE_WAVECOUNTS[note_index]
            print("desired log wavecount: ", dwc)
            #error_tolerance = int(dwc * 0.00025)  # % error rather than a static number
            error_tolerance = 5  # note this is right at the limit of resolution for higher frequencies
            # could use a higher clock speed state machine for the higher freqs?
            # which would represent a different tolerance depending on the absolute value

            corxn = 0
            coarse = self.note_to_dac_signals(note_index)  # uses line fit and floats

            # first, optimize the coarse value that is closest to the desired freq - want to avoid crossing over
            # coarse increments during fine tuning

            send_dac_value(self.f, 127)
            last_delta = 999999
            delta = 0
            increment = 1
            flipped = False
            while 1:
                print("in coarse loop, coarse = ", coarse)
                send_dac_value(self.c, coarse)
                time.sleep(0.001)
                hi, lo, cnt = get_sample_reject_anomalies(min_samples=4)
                wc = (hi + lo) // cnt
                log_freq = fast_log2(wc)
                delta = abs(dwc - log_freq)
                if delta > last_delta:
                    if flipped:
                        coarse -= increment  # restore the previous value which turns out to be the best - "step back"
                        break
                    increment *= -1
                    flipped = True
                last_delta = delta
                coarse += increment

            print("finished optimizing coarse value")

            print(f"for note {note_index} sending {coarse} to dac")
            print("allowed error is: ", error_tolerance)
            print("step\terror\tEMA\tcorrection")

            send_dac_value(self.c, coarse)
            send_dac_value(self.f, 127)  # start by centering fine
            inc = 0
            err = 999  # arbitrary to start loop
            error_counter = 0

            # need to see more than this number of samples with error within tolerance to pass
            corrected = False
            error_alpha = 1800  # 0 to 4090 and determines the smoothing of the EMA on the error
            fine_alpha = 1800  # ditto and smooths the PID output value that we capture at the end
            error_ema = 999
            fine_ema = 999
            out_of_range_count = 0  # only change coarse increment if we sent 3 corrections out of range

            #while abs(err) > error_tolerance:
            #while error_counter < error_count_threshold:
            while abs(error_ema) > error_tolerance:

                if not corrected:
                    if abs(err) < error_tolerance:
                        error_counter += 1
                    else:
                        error_counter = 0  # reset and keep hunting

                    if corxn > 255:  # TODO: DRY
                        out_of_range_count += 1
                        if out_of_range_count > 2:
                            coarse += 1
                            send_dac_value(self.c, coarse)
                            send_dac_value(self.f, 0)
                            self.pid.reset()
                            out_of_range_count = 0
                            # just re-centre fine to put us the furthest distance away from another coarse jump
                    elif corxn < 0:
                        out_of_range_count += 1
                        if out_of_range_count > 2:
                            coarse -= 1
                            send_dac_value(self.c, coarse)
                            send_dac_value(self.f, 0)
                            self.pid.reset()
                            out_of_range_count = 0
                    else:
                        send_dac_value(self.f, corxn)

                    send_dac_value(self.f, corxn)
                    corrected = True

                #measured = (hi + lo) // count  # measurement of the actual wavecycle time
                measured, stale = get_frequency_ema(min_samples=3)
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
                error_ema = ((error_alpha * err) + ((4096 - error_alpha) * error_ema)) >> 12
                fine_ema = ((fine_alpha * corxn) + ((4096 - fine_alpha) * fine_ema)) >> 12
                tnow = time.ticks_us()
                # print(f"calculated correction: {corxn}")
                print(f"{tnow}\t{err}\t{error_ema}\t{corxn}")
                inc += 1

            self.coarse_array[note_index] = coarse
            #self.fine_array[note_index] = corxn
            self.fine_array[note_index] = fine_ema  # use the smoothed PID outputs during the same period
            # that the error was smoothed
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
