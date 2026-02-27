from math import log2

# module for establishing the gradient of the V vs log(F) line for an oscillator. Then we can calculate the
# required voltage for a given desired frequency.
# work with clock counts rather than frequencies to use big ints rather than floats. (Does it matter?)

SM_FREQ = 6E6  # clock frequency the frequency counting PIOs are running at

class Tuner:
    
    """object for storing pairs of (voltage, freq) and calculating tuning curve
    voltage is an 8-bit value from 0 to 255 for the 8-bit DAC"""
    
    def __init__(self, size=4):
        
        self.size = size
        self.xs = [0.0] * size
        self.ys = [0.0] * size
        self.index = 0
        self.m = 0
        self.c = 0
        self.lastx = 0  # use this to reject samples that are too close to the one we just recorded
        # otherwise we might get all our points bunched up and fit becomes unstable


    def add(self, x, y):
        
        delta = abs(x - self.lastx)
        if delta > 10:  # only save a sample that's sufficiently different from the previous one
            self.index = (self.index + 1) % self.size  # circular buffer behaviour
        else:
            print("tuner got too similar value, overwriting without incrementing")
        self.xs[self.index] = x
        self.ys[self.index] = log2(SM_FREQ/y)  # exponential  response of F on V
        self.lastx = x


    def fit_line(self):
        
        """Take the (voltage, wave count) values from the sample and get the linear fit parameters
        returns m and c from y = mx + c"""
        
        n = len(self.xs)

        sum_x = 0.0
        sum_y = 0.0
        sum_xx = 0.0
        sum_xy = 0.0

        # linear regression apparently

        for i in range(n):
            x = self.xs[i]
            y = self.ys[i]
            sum_x += x
            sum_y += y
            sum_xx += x * x
            sum_xy += x * y

        denom = n * sum_xx - sum_x * sum_x
        if denom == 0:
            return None  # all x are equal → vertical line

        self.m = (n * sum_xy - sum_x * sum_y) / denom
        self.c = (sum_y - self.m * sum_x) / n
        
    def fit_correction_line(self):
        
        """once we have the initial fit, there is a second order term we need to apply (apparently??)"""
        
        pass
        
    
    def clocks_to_voltage(self, cnt):
        
        """What voltage do I need to generate a wave with this many clocks per cycle?"""
        
        wanted = log2(SM_FREQ/cnt)
        return (wanted - self.c)/self.m
        
        
    """
    def freq_to_voltage(self, freq):
        
        # If I want this freq, what voltage do I need to send in? 
        # i.e. what value of x gives this desired value of y
        
        return int((log2(freq) - self.c)/self.m)  # rearranged y = mx + c
        # must be an int because DACs expect an 8-bit value
    """
