"""
Fader channels
73, 75, 79,72,80,81,82,83,85

knobs
74,71,76,77,93,18,19,16,17
"""


class MyVariable:

    def __init__(self, default, min_val, max_val):

        """Clamps the value between max and min"""

        self._value = default
        self._min_val = min_val
        self._max_val = max_val

    def get(self):

        return self._value

    def set(self, val):

        if val > self._max_val:
            self._value = self._max_val
        elif val < self._min_val:
            self._value = self._min_val
        else:
            self._value = val


class MyCategory:

    pass






class LookUp:

    """lets us look up a parameter by doing ParamsInterface.Property rather than PARAMS['PROPERTY']"""

    def __getattr__(self, item):

        return PARAMS[item].get()


class PhysicalControlsDict:

    """Maps the parameters dictionary to a range of ints so that a key can be selected with the hardware
    rotary encoder (1-127). Emits a signal when the current selected key is changed by updating the
    stored encoder position. When sent a value from the setting slider, it will assign that value to
    the currently selected variable."""

    def __init__(self):

        l = len(PARAMS)  # how many slices to we need to divide the range into?
        self.divisor = 127//l  # size of one "slice" of the list, this sets the "divisor" for the address integer
        self.remainder = 127 - l * self.divisor
        self.key_list = sorted(list(PARAMS.keys()))
        self.current = self.key_list[0]
        self.last_parameter_updated = None

    def update_address(self, addr):

        a = (addr - self.remainder - 1) // self.divisor
        #a = min(a, len(self.key_list))  # avoid indexerror when we try to look in the remainder
        p = self.key_list[a]
        if not p == self.current:
            self.current = p
            return p, PARAMS[p].get(), True # return the current key only when it changes, so we can update the display
        return None, None, None  # needs to look like an unpackable tuple

    def update_value(self, val):

        PARAMS[self.current].set(val)
        #return f"{self.current}:\n{val}"  # TODO: make more efficient

    def read_value(self):

        return PARAMS[self.current].get()

    def update_channel(self, chan, val):

        """Directly update a parameter that is bound to a physical control. Return the name of the parameter
        and the value it was set to. Those return values are used to decide whether we update the LCD."""

        # print(chan, val)
        refresh = False  # by default assume we don't want to change the displayed param name
        if chan == 17:  # hardcoded - rightmost knob, for selecting parameters
            return self.update_address(val)
        elif chan == 85:  # hardcoded - rightmost slider
            self.update_value(val)
            return None, val, None

        v = CHANNELS.get(chan, None)
        val *= 2  # keyboard controls are 0-127# !!!! by default, multiply keyboard controls via 2.
        # They are 0-127 but internally
        # we are using 8-bit values from 0-255
        if not v:
            v = self.current  # if we didn't find anything, then the user is wanting to bind this control to whatever
            # was selected with the rightmost knob
            # return None, None
            CHANNELS[int(chan)] = v  # do the binding

        PARAMS[v].set(val)

        if not v == self.current:
            self.current = v
            disp = v
            refresh = True
        else:
            disp = v  # always want to send the signal that we changed this
            # this is all awful and needs to be redone
        return disp, val, refresh  # so we can display what value we are changing
        # only worth returning the parameter name if it did in fact change


def write_params():

    inverted_chan = {v:k for k,v in CHANNELS.items()}

    with open("SETTINGS", "w") as f:
        for k, v in PARAMS.items():
            chan = inverted_chan[k]
            f.write(f"{k} {v.get()} {chan}\n")
    print("saved parameters")


# code on module load - read in settings from file

PARAMS = {}
CHANNELS = {}  # for mapping physical controls to any parameter

with open("SETTINGS", "r") as f:
    for line in f.readlines():
        line = line.rstrip("\n")
        varname, val, chan = line.split(" ")  # chan is whichever slider on the keyboard we set up with midi learn
        PARAMS[varname] = MyVariable(int(val), 0, 255)  # hardcoding max and min for now
        CHANNELS[int(chan)] = varname





