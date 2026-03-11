from mydacs import send_dac_value
import ADSR2
from freq_count_nodma import freq_count_reset
from filtertable import FILTER_CVS
from oscillator import Oscillator

class Voice:

    def __init__(self, mods, retune=True, cutoff_freq_tracking=True):

        # setting static values but in future these will be args

        self.identity = 0  # HARDCODED for now, but this is the "caller" argument for mod sources

        # !! HACK ALERT - PWM INDEX IS HARDCODED HERE !! #
        if retune:
            send_dac_value(3, 127)
            # regardless of what it was set to before, need ca. 50% duty cycle to get good measurements

        self.osc = Oscillator(4, 5)  # we are manually specifying coarse and fine DAC index here
        # eventually need to give voice an address as well for polyphonic

        # hacky way to specify values during empirical PID tuning
        # 512, 128, 128 seem good!!
        # not any more when changing to EMA.......
        # 1024 512 1024 sems good ish
        # changed res to 16000 (14 bit)
        self.osc.pid.p = 6000
        self.osc.pid.i = 36
        self.osc.pid.d = 4096

        self.osc.setup(retune=retune)

        self.monitoring = False  # set to true when this voice is connected to the tune bus for monitoring. Then we can
        # get corrections from the oscillator PID to autotune the frequency and apply it with the rest of the
        # modulations

        # indices of the DAC channels that control these parameters
        self.xfade_idx = 0  # actually external mix now TODO
        self.suboctave_idx = 1
        self.pwm_idx = 3
        self.envelope_idx = 2
        self.resonance_idx = 7
        self.cutoff_idx = 6

        # these values are pushed into the voice class from the main loop update function
        # all are always values from 0 to 255 to match the DAC's expected input values
        self.coarse = 0
        self.fine = 0
        self.xfade = 0
        self.suboctave = 0
        self.pwm = 0
        self.envelope = 0
        self.resonance = 0
        self.cutoff = 0

        self.filter_track = 0  # signal added to the filter output to track with volts/octave

        # we need to put these in a list so we can access the variables for applying modulation sources:
        # self.variable_names = ["coarse", "fine", "xfade", "suboctave", "pwm", "envelope", "resonance", "cutoff"]
        self.variable_names = ["xfade", "suboctave", "envelope", "pwm", "coarse", "fine", "cutoff", "resonance"]
        # we are storing names because we use getattr. Would probably be better to just do by list index
        # TODO: by list index instead

        self.last_sent = [0, 0, 0, 0, 0, 0, 0, 0]  # don't update a DAC if the value hasn't changed. Use this
        # to keep track of the last value we sent to the DAC for a given channel

        # current statuses
        self.note_down = False
        self.cutoff_freq_tracking = cutoff_freq_tracking  # TODO: configurable later

        self.modulation_assignments = mods  # a list where the index is the DAC channel and the list entry is
        # a list of objects we should query via their get() method to get a modulation amount
        # so [[], [LFO1]] means nothing is applied to channel 0 and LFO1 is applied to channel 1

        self.adsrs = []
        # build a list of ADSR objects that modulate this voice. We need this in order to send gate signals
        # when the note is turned on/off
        for ls in self.modulation_assignments:
            for entity in ls:
                if type(entity) == ADSR2.ADSR:
                    self.adsrs.append(entity)

    def send(self, note_down, midinote=None):

        # receive an instruction from the main loop to play a note
        # expects a midi note index

        if self.monitoring:
            freq_count_reset()  # throw out old freq measurements otherwise the new note correction signal
            # will be based on the old frequency

        if note_down and not self.note_down:
            self.note_down = True

            if midinote:
                self.coarse, self.fine = self.osc.play_note(midinote)
                if self.cutoff_freq_tracking:
                    self.filter_track = FILTER_CVS[midinote]
                for envelope in self.adsrs:
                    envelope.gate(self.identity, True)  # envelopes will start attacking

        elif not note_down and self.note_down:
            self.note_down = False
            for envelope in self.adsrs:
                envelope.gate(self.identity, False)  # tell envelopes to release
            # we can grab this voice for another purpose if needed in which case the envelopes are remembering
            # their own states and won't "glitch" if restarted

    def update(self):

        # TODO: don't bother get'ing from a mod source that isn't in use
        coarse_correction = fine_corrected = 0
        if self.monitoring:
            pass
            # coarse_correction, fine_corrected = self.osc.correct()  # TODO - correction function changed
            # print("freq corrections coarse and fine were: ", coarse_correction, fine_corrected)

        for idx, ls in enumerate(self.modulation_assignments):
            modulation_sum = 0  # TODO: what if we want to multiply modulations, not add?
            for entity in ls:
                # print(entity)
                # print(entity.get(self.identity))
                modulation_sum += entity.get(self.identity) >> 8  # mod sources are higher-res
                # TODO - just decide on a resolution and stick to it!! Voices should be 16-bit too

            base_variable = self.variable_names[idx]  # so we can refer by name

            # overwrite coarse and fine if they need correction
            if base_variable == "coarse" and coarse_correction != 0:
                self.coarse += coarse_correction
            elif base_variable == "fine" and fine_corrected != 0:
                self.fine = fine_corrected

            # print(f"for {base_variable}, modsum = {modulation_sum}")

            modulation_sum += getattr(self, base_variable)  # add the base value around which we modulate

            # print("now ", modulation_sum)

            if base_variable == "cutoff":
                modulation_sum = 255 - modulation_sum  # HACK ALERT! The filter is BACKWARDS LOL
                # in the circuit higher CV -> lower cutoff, so this inversion makes it so high CV -> more open

            if self.last_sent[idx] == modulation_sum:
                pass  # don't bother sending a DAC signal at all if nothing changed
            else:
                # print("sending", modulation_sum, "to", idx)
                send_dac_value(idx, modulation_sum)
                self.last_sent[idx] = modulation_sum

    def export(self):

        out = []
        for v in self.variable_names:
            out.append(getattr(self, v))

        return out

    def load(self, ls):

        for i in range(len(ls)):
            varname = self.variable_names[i]
            setattr(self, varname, ls[i])