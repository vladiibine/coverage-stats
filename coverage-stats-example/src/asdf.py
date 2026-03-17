"""This is a test module"""

X = "module-level constant"
4
def calc_stuff():
    return {
    x: x**2
    for y in [[1,2,3], [4,5,6]]
    for x in y
    if x+4 < 300
}
x = calc_stuff()
y = {
    x: x**2
    for y in [[1,2,3], [4,5,6]]
    for x in y
    if x+4 < 300
}

class Barbeque:
    """The docstring."""
    def __init__(self, a, b):
        """The docstring - this will not be tested, but the init and class definition line are counted as covered."""
        self.a = a
        self.b = b


"This is a random string"
# This is a comment
def foo_sum(a, b):
    #
    x = 1
    "another random string"
    return a + b


def double_sum(a, b, c):
    if a < 10000000:
        return foo_sum(foo_sum(a, b), c)
    # return 1


def multiply_sum(a, b, c):
    """Does (a+b)*c."""
    return foo_sum(a, b) * c


def not_covered(a, b):
    """The docstring."""
    class TotallyNotCovered:
        """The docstring."""
        def __init__(self, a, b):
            """The docstring."""
            self.a = a
            self.b = b
    print(TotallyNotCovered(a, b))
