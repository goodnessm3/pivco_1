"""
# code that generates the table. But we will just hardcode it.

import math

def generate_log2_lut(entries=32, scale=4096):
    lut = []
    for i in range(entries + 1):
        # Calculate log2(1 + i/entries)
        val = math.log2(1 + (i / entries))
        lut.append(round(val * scale))
    return tuple(lut)

# Generate for 32 segments
LOG2_LUT_12BIT = generate_log2_lut(32, 4096)  # it's better to make this a local variable in the fast log func
"""

# apparently accessing a tuple is slightly faster than accessing an array because the values are stored
# in the pointers themselves??
LOG2_LUT_12BIT = (0, 182, 358, 530, 696, 858, 1016, 1169, 1319, 1465, 1607, 1746, 1882, 2015, 2145, 2272, 2396, 2518,
 2637, 2754, 2869, 2982, 3092, 3200, 3307, 3412, 3514, 3615, 3715, 3812, 3908, 4003, 4096)

def bit_length(x):

    """Available natively in Python but not micropython!!!"""

    if x == 0:
        return 0
    # For positive numbers
    num_bits = 0
    temp = abs(x)
    while temp > 0:
        temp >>= 1
        num_bits += 1
    return num_bits


def fast_log2(x, _lut=LOG2_LUT_12BIT):
    """
    Returns the log2 * 4096 of the input, used to scale our measured wave cycle times into a linear scale for the PID
    Accurate to within 0.003%
    vibe coded with Gemini because I'm such a noob
    """

    if x <= 0: return 0

    #  msb = x.bit_length() - 1  # in "actual" Python this is a method of ints
    msb = bit_length(x) - 1

    # 1. Get 12-bit fractional part (0-4095)
    if msb >= 12:
        frac = (x >> (msb - 12)) & 0xFFF
    else:
        frac = (x << (12 - msb)) & 0xFFF

    # 2. Split 12-bit fraction into:
    # index: top 5 bits (0-31) to pick the LUT entry
    # rem:   bottom 7 bits (0-127) to interpolate between entries
    index = frac >> 7
    rem = frac & 0x7F

    # 3. Linear Interpolation between LUT entries
    # base_val + (slope * remainder)
    # The slope is (next_val - base_val) / 128
    base_val = _lut[index]
    diff = _lut[index + 1] - base_val

    # (diff * rem) >> 7 is the same as (diff * rem) / 128
    # Max value: 182 * 127 = 23,114 (Well within 31-bit limit)
    interpolated_frac = base_val + ((diff * rem) >> 7)

    return (msb << 12) + interpolated_frac