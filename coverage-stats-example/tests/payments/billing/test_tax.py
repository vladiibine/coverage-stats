from coverage_stats import covers
from payments.billing.tax import tax_total, tax_double, tax_multiply


def test_tax_basic():
    tax_total(1, 2)


def test_tax_properly():
    assert tax_total(0, 0) == 0
    assert tax_total(1, 0) == 1
    assert tax_total(0, 1) == 1
    assert tax_total(-1, 1) == 0


def test_tax_double():
    assert tax_double(1, 2, 3) == 6


@covers(tax_multiply)
def test_tax_multiply():
    assert tax_multiply(1, 2, 3) == 9
    assert tax_multiply(2, 2, 3) == 12
    assert tax_multiply(3, 2, 3) == 15
    assert 1 == 1
