from array import array
import math

def freq2cv(freq):

    """Expects frequency in Hz. Experimentally determined from filter setup and based on the assumption that
    we are inverting the control signal, that is, sending 255 sends 0 volts and sending 0 sends 5 volts. Either
    I have wired the filter up backwards or the chip is just designed that way."""

    return (math.log10(freq/1000.0) + 0.64) / 7.27E-3



A1 = 55.00
FILTER_CVS = array("B", [0] * 33)
# going from A1 as it's the lowest integer number
for x in range(100):
    freq = round(A1 * 2**(x/12.0),2)
    cv = max(0.0, freq2cv(freq))
    if int(cv) > 255:
        break
    FILTER_CVS.append(int(cv))

# FILTER_CVS is a table where the midi note (index in the table) corresponds to the filter CV required to get
# that cutoff frequency. We are generally going to want a cutoff much higher than the actual note. The filter is
# configured to have an offset that is added to this control voltage.