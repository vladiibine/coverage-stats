"""Compliance operations."""

X = "module-level constant"
4


def calc_stuff():
    return {
        x: x**2
        for y in [[1, 2, 3], [4, 5, 6]]
        for x in y
        if x + 4 < 300
    }


x = calc_stuff()


class ComplianceService:
    """Service for compliance domain logic."""

    def __init__(self, id_, name):
        self.id_ = id_
        self.name = name


def compliance_total(a, b):
    x = 1
    return a + b


def compliance_double(a, b, c):
    if a < 10000000:
        return compliance_total(compliance_total(a, b), c)


def compliance_multiply(a, b, c):
    """Does (a+b)*c."""
    return compliance_total(a, b) * c


def compliance_uncovered(a, b):
    """Not covered by tests."""
    return a - b
