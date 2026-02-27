"""
attack equation = y = 10 ^ ( (-t/1000) / atk_const ) where t is in ms and y is a value from 0 to 1
if we define the end of the envelope as y = 0.9, for some reason, atk_const = the time in s we want it to take to reach this.
let's define finishing as 99% extent which is reached after 2 * atk const.

"""

class ADSR:

    def __init__(self, atk_time, dky_time, rel_time, sus_level, inverted=False):

        # atk, dky, and rel_time are times in milliseconds for each phase to last.
        # these are converted to constants in this init method.
        # sus_level is the extent we sustain at after the decay phase.
        self.atk_end = atk_time
        self.dky_end = atk_time + dky_time
        self.atk = atk_time/2000.0
        self.dky = dky_time/2000.0
        self.rel = rel_time/2000.0
        self.sus_level = float(sus_level)
        self.window = 0.99 - self.sus_level  # the range the decay needs to scale to
        self.inverted = inverted

    def attack_point(self, t):
        
        return 1-(10**(-1*t/1000.0/self.atk))
        
    def release_point(self, t):

        ret = 10**(-1*t/1000.0/self.rel)*self.sus_level
        if ret > 0.01:
            return ret
        return 0

    def decay_point(self, t):

        t = t - self.atk_end
        return 10**(-1*t/1000.0/self.dky)*self.window + self.sus_level

    def get_level_internal(self, t, held=True):

        # when held = false we are in the release phase
        
        if held:
            if t <= self.atk_end:
                return self.attack_point(t)
            elif self.atk_end < t < self.dky_end:
                return self.decay_point(t)
            elif t >= self.dky_end:
                return self.sus_level
        else:
            return self.release_point(t)
        
        
    def get_level(self, t, held=True):
        
        if self.inverted:
            return 1 - self.get_level_internal(t, held)
        else:
            return self.get_level_internal(t, held)


