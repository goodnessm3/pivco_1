from math import log2

# module for establishing the gradient of the V vs log(F) line for an oscillator. Then we can calculate the
# required voltage for a given desired frequency.
# work with clock counts rather than frequencies to use big ints rather than floats. (Does it matter?)

SM_FREQ = 6E6  # clock frequency the frequency counting PIOs are running at

class Fitter:
    
    def __init__(self, size=4, difference_threshold=10):
        
        self.size = size
        self.difference_threshold = difference_threshold
        self.xs = [0.0] * size
        self.ys = [0.0] * size
        self.index = 0
        self.m = 0
        self.c = 0
        self.lastx = 0  # use this to reject samples that are too close to the one we just recorded
        # otherwise we might get all our points bunched up and fit becomes unstable


    def add(self, x, y):
        
        delta = abs(x - self.lastx)
        if delta > self.difference_threshold:  # only save a sample that's sufficiently different from the previous one
            self.index = (self.index + 1) % self.size  # circular buffer behaviour
        #else:
            #print("tuner got too similar value, overwriting without incrementing")
        self.xs[self.index] = x
        self.ys[self.index] = y  # exponential response of F on V
        self.lastx = x


    def fit_line(self):
        
        """returns m and c from y = mx + c"""
        
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
                
    
    def getx(self, y):

        return (y - self.c)/self.m
        
    def gety(self, x):
                
        return self.m * x + self.c
        
        