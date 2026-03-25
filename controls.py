from myutils import listindex, fpmult

############################
### HARDCODED CONTROL MAPPINGS ###

adsr_parameter_mapping = {
    74: "a",
    71: "d",
    76: "s",
    77: "r",
    93: "depth"
}

lfo_parameter_mapping = {81: "rate", 82: "depth", 83: "shape"}

voice_parameter_mapping = {
    73: "suboctave",
    75: "cutoff",
    79: "resonance",
    72: "pwm",
    80: "xfade"  # CHECK!! this is probably for the breadboard version but NOT the PCB version
}

option_lists = {"shape":["SAW", "RAMP", "TRI", "SINE", "SHARK"],
                "invert": ["ON", "OFF"]
               }

adsr_keys = list(adsr_parameter_mapping.keys())
lfo_keys = list(lfo_parameter_mapping.keys())
voice_keys = list(voice_parameter_mapping.keys())

objtypes = {}  # maps a numeric channel to a tuple of name and a dict of all its possible parameters
# lets us look up what kind of object we are controlling based on a hardcoded control number
for k in adsr_keys:
    objtypes[k] = ("ADSR", adsr_parameter_mapping)
for k in lfo_keys:
    objtypes[k] = ("LFO", lfo_parameter_mapping)
for k in voice_keys:
    objtypes[k] = ("VOICE", voice_parameter_mapping)

#################################


class Controls:

    def __init__(self, voice_list, lfo_list, adsr_list, shutdown_handler):

        """Pass in lists of modulators which were instantiated in the main thread. We will just refer to these by number index 1..5"""

        self.voice_list = voice_list
        self.lfo_list = lfo_list
        self.adsr_list = adsr_list
        self.selected_property = None  # what variable are we currently looking at?
        self.selected_adsr = adsr_list[0]  # indexing the list we were passed on instantiation
        self.selected_lfo = lfo_list[0]
        self.selected_voice = voice_list[0]
        self.selected_object = ""  # this is just a text label to show on the LCD what we are editing
        self.updated = []  # a queue of updated parameters to provide to the main loop when asked
        # tuples of object, property and value
        # mainloop will do object.__setattr__(value)
        self.printable_names = self.make_printable_names()
        self.shutdown_handler = shutdown_handler  # reference to the function to run if we want to turn off

    def make_printable_names(self):

        dc = {}
        for i, j in enumerate(self.voice_list):
            dc[j] = f"VOICE {i + 1}"
        for i, j in enumerate(self.lfo_list):
            dc[j] = f"LFO {i + 1}"
        for i, j in enumerate(self.adsr_list):
            dc[j] = f"ADSR {i + 1}"
        return dc

    def process_control_signal(self, channel, value):

        # these won't be set if we are changing the selected ADSR/LFO, still need to update
        # the display with the identity of the changed object though
        param_name = None
        object_type = None

        if channel == 17:  # param select knob,
            return  # TODO - fill in later
        elif channel == 85:  # generic entry for any value
            return  # TODO - fill in later
        elif channel == 23:
            if value > 127:
                print("tap button - use for graceful shutdown")  # TODO
                self.shutdown_handler()  # run the shutdown function
            return
        elif channel == 19:  # envelope select
            self.selected_adsr = listindex(self.adsr_list, value)
            self.selected_object = "ADSR"
            actual_object = self.selected_adsr
            value = None
        elif channel == 16:  # lfo select
            self.selected_lfo = listindex(self.lfo_list, value)
            self.selected_object = "LFO"
            actual_object = self.selected_lfo
            value = None
        else:
            try:
                object_type, object_params = objtypes[channel]
            except KeyError:
                return  # don't care about control we don't know about
            param_name = object_params[channel]

            self.selected_property = param_name
            self.selected_object = object_type

            if object_type == "VOICE":
                actual_object = self.selected_voice
            elif object_type == "LFO":
                actual_object = self.selected_lfo
            elif object_type == "ADSR":
                actual_object = self.selected_adsr

        if object_type == "VOICE":  # slightly temporary, just update all voice objects the same
            for q in self.voice_list:
                self.updated.append((q, param_name, value))
        else:
            self.updated.append((actual_object, param_name, value))  # this is used to update objects in the main thread

    def get_updated(self):

        """Returns a list of variables that have changed since the last time we checked. The main loop uses this to
        tell objects they need to update themselves"""

        out = []
        while len(self.updated) > 0:
            out.append(self.updated.pop())
        return out


class DisplayManager:

    def __init__(self, voice_list, lfo_list, adsr_list):

        self.voice_list = voice_list
        self.lfo_list = lfo_list
        self.adsr_list = adsr_list
        self.line1 = ""
        self.line2 = ""

    def update(self, update_tup):

        line1, line2 = self.get_lines(update_tup)
        diff1 = self.diff_line(self.line1, line1)
        diff2 = self.diff_line(self.line2, line2)

        self.line1 = line1
        self.line2 = line2

        return diff1, diff2  # lists of tuples [(index, run of characters)]
        # this lets us only update the LCD characters that have changed

    def get_lines(self, update_tup):

        actual_object, param_name, value = update_tup  # unpacking the tuple generated by the Controls object
        printable_index = 999  # a placeholder indicator that something has gone very wrong
        for ls in self.voice_list, self.lfo_list, self.adsr_list:
            if actual_object in ls:
                # so the user can see LFO1, LFO2...
                printable_index = ls.index(actual_object) + 1
                break

        if actual_object in self.adsr_list or actual_object in self.lfo_list:
            # these objects are printable so we just pretty print them and insert their number
            outa, outb = actual_object.pretty_print()
            outa %= printable_index

        elif actual_object in self.voice_list:
            # can't fit all voice params on one display so we just display one at a time
            outa = "VOICE %i" % printable_index
            outb = "%s: %i" % (param_name, value)  # todo: pretty conversion e.g. cutoff into Hz

        return outa, outb

    def diff_line(self, old_line, new_line):

        """Detect only the characters that changed"""

        while len(new_line) < len(old_line):
            new_line += " "  # add spaces to overwrite the longer old line

        oldlen = len(old_line)
        newlen = len(new_line)

        minlen = min(oldlen, newlen)

        runs = []  # start index and a run of characters that need to be replaced
        index = 0

        runstart = 0
        run = []
        accumulating = False

        while index < minlen:
            old = old_line[index]
            new = new_line[index]

            if old == new:
                if run:  # don't append the empty list first time round
                    accumulating = False
                    runs.append((runstart, run))
                    runstart = 0
                    run = []
            else:
                if not accumulating:
                    accumulating = True
                    runstart = index
                run.append(new)

            index += 1

        if accumulating:  # make sure we catch the run if the line was different right
            # up until the last character
            runs.append((runstart, run))

        if oldlen < len(new_line):
            runs.append((oldlen, new_line[oldlen:]))

        return runs