"""Discounts operations."""

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


class DiscountsService:
    """Service for discounts domain logic."""

    def __init__(self, id_, name):
        self.id_ = id_
        self.name = name


def discounts_total(a, b):
    x = 1
    return a + b


def discounts_double(a, b, c):
    if a < 10000000:
        return discounts_total(discounts_total(a, b), c)


def discounts_multiply(a, b, c):
    """Does (a+b)*c."""
    return discounts_total(a, b) * c


def discounts_uncovered(a, b):
    """Not covered by tests."""
    return a - b
