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


def weird_corner_cases_1_while_loop_(a, b):
    """Weird corner cases 1."""
    while a:
        a.pop()

    a.append(b)

    while a:
        b.pop()

    return 4


def weird_corner_cases_2_for_loop(a, b):
    """Weird corner cases 2."""
    counter = 9
    for x in a:
        counter += 3

    for x in b:
        counter += 30

    return 15

def weird_case_multiple_statements_on_one_line(a, b):
    """Weird corner cases 2."""
    x = 1; y = 2; z = 3

    q = 3 if a == 2 else 4
    w = 4 if a == 2 else 5 if b == 3 else 6
    e = 5 if a == 2 else 0; r = 0 if a == 2 else -1


def weird_corner_cases_3_try_except_(a):
    """try-except-else: only the exception branch is ever taken."""
    try:
        x = 10 // a
    except ZeroDivisionError:
        x = -1
    else:
        x = x + 1  # never reached — a is always 0
    return x


def not_covered(a, b):
    """The docstring."""
    class TotallyNotCovered:
        """The docstring."""
        def __init__(self, a, b):
            """The docstring."""
            self.a = a
            self.b = b
    print(TotallyNotCovered(a, b))
