from array import array
from fastlog2 import fast_log2

SM_FREQ = 6_000_000

# lowest note on keyboard = 36
# highest note = 96

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