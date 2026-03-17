from coverage_stats import covers
from payments.gateway.paypal import paypal_total, paypal_double, paypal_multiply


def test_paypal_basic():
    paypal_total(1, 2)


def test_paypal_properly():
    assert paypal_total(0, 0) == 0
    assert paypal_total(1, 0) == 1
    assert paypal_total(0, 1) == 1
    assert paypal_total(-1, 1) == 0


def test_paypal_double():
    assert paypal_double(1, 2, 3) == 6


@covers(paypal_multiply)
def test_paypal_multiply():
    assert paypal_multiply(1, 2, 3) == 9
    assert paypal_multiply(2, 2, 3) == 12
    assert paypal_multiply(3, 2, 3) == 15
    assert 1 == 1
