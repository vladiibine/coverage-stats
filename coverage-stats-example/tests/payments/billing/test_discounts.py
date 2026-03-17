from coverage_stats import covers
from payments.billing.discounts import discounts_total, discounts_double, discounts_multiply


def test_discounts_basic():
    discounts_total(1, 2)


def test_discounts_properly():
    assert discounts_total(0, 0) == 0
    assert discounts_total(1, 0) == 1
    assert discounts_total(0, 1) == 1
    assert discounts_total(-1, 1) == 0


def test_discounts_double():
    assert discounts_double(1, 2, 3) == 6


@covers(discounts_multiply)
def test_discounts_multiply():
    assert discounts_multiply(1, 2, 3) == 9
    assert discounts_multiply(2, 2, 3) == 12
    assert discounts_multiply(3, 2, 3) == 15
    assert 1 == 1
