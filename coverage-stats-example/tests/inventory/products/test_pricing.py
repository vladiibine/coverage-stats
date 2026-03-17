from coverage_stats import covers
from inventory.products.pricing import pricing_total, pricing_double, pricing_multiply


def test_pricing_basic():
    pricing_total(1, 2)


def test_pricing_properly():
    assert pricing_total(0, 0) == 0
    assert pricing_total(1, 0) == 1
    assert pricing_total(0, 1) == 1
    assert pricing_total(-1, 1) == 0


def test_pricing_double():
    assert pricing_double(1, 2, 3) == 6


@covers(pricing_multiply)
def test_pricing_multiply():
    assert pricing_multiply(1, 2, 3) == 9
    assert pricing_multiply(2, 2, 3) == 12
    assert pricing_multiply(3, 2, 3) == 15
    assert 1 == 1
