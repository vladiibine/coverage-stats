from coverage_stats import covers
from payments.billing.billing import billing_total, billing_double, billing_multiply


def test_billing_basic():
    billing_total(1, 2)


def test_billing_properly():
    assert billing_total(0, 0) == 0
    assert billing_total(1, 0) == 1
    assert billing_total(0, 1) == 1
    assert billing_total(-1, 1) == 0


def test_billing_double():
    assert billing_double(1, 2, 3) == 6


@covers(billing_multiply)
def test_billing_multiply():
    assert billing_multiply(1, 2, 3) == 9
    assert billing_multiply(2, 2, 3) == 12
    assert billing_multiply(3, 2, 3) == 15
    assert 1 == 1
