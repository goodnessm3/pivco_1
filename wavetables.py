from array import array
import math

DEFAULT_RESOLUTION = 200  # default number of points that describe one cycle of the function

def build_expo_array(npoints=DEFAULT_RESOLUTION):

    """build a lookup table for y=1/(10**x)"""

    # expo functions - default is to decay to 10% after 1 second
    # y = 1/(10^t) decays to 0.1 in 1s, and then 0.01 in 2s

    arr = array("H", [])  # using H (unsigned short) - all envelopes and LFOs will be positive modulation values
    step_size = 2.0 / npoints
    t = 0
    while t < 2.0:
        v = 1 / (10 ** t)
        vint = int(v * 65535) - 1  # convert our frac from 0 to 1 to cover the max range of our 16 bit integer
        arr.append(vint)
        t += step_size

    return arr


def build_saw_array(npoints=DEFAULT_RESOLUTION):

    arr = array("H", [])  # unsigned short
    step_size = 65535 // npoints
    v = 0
    index = 0
    for _ in range(npoints):
        arr.append(v)
        v += step_size

    return arr


def build_ramp_array(saw_array, npoints=DEFAULT_RESOLUTION):

    arr = array("H", [])  # unsigned short
    for v in saw_array:
        arr.append(65535 - v)

    return arr


def build_triangle_array(saw_array, npoints=DEFAULT_RESOLUTION):

    arr = array("H", [])  # unsigned short

    even = True  # array step other than 1 not supported in micropython!??!?!

    #for v in saw_array[::2]:
    for v in saw_array:
        if even:
            arr.append(v)
        even = not even
    # now walk backwards thru the array, mirroring it
    index = len(arr) - 1
    while len(arr) < npoints:
        arr.append(arr[index])
        index -= 1

    return arr


def build_sine_array(npoints=DEFAULT_RESOLUTION):

    arr = array("H", [])  # unsigned short
    increment = 2 * math.pi / npoints
    i = 0
    while len(arr) < npoints:
        f = math.sin(i)
        arr.append(int((f + 1) * 32767))
        i += increment
    return arr


def build_sharkfin_array(expo_array, npoints=DEFAULT_RESOLUTION):

    arr = array("H", [])  # unsigned short

    even = True

    for v in expo_array:
        if even:
            arr.append(v)
        even = not even
    # now walk backwards thru the array
    even = True

    for v in expo_array:
        if even:
            arr.append(65535 - v)
        even = not even

    return arr


#  on startup, build lookup tables for the LFOs and ADSRs to get their values
EXPO = build_expo_array()
SAW = build_saw_array()
RAMP = build_ramp_array(SAW)
TRI = build_triangle_array(SAW)
SINE = build_sine_array()
SHARK = build_sharkfin_array(EXPO)