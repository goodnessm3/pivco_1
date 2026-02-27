def listindex(ls, val):

    """use a value of 0-255 to look up something in a list.
    Regardless of list length, 255 is divided evenly among its items"""

    index = (len(ls) * val) // 255
    return ls[index]

def fpmult(a, b):

    """Scale 'a' down by a factor b of 0-65536 (returns a * (b/65536))"""

    c = a * b
    return c >> 16