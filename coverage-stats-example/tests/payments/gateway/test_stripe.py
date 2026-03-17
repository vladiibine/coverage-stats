from coverage_stats import covers
from payments.gateway.stripe import stripe_total, stripe_double, stripe_multiply


def test_stripe_basic():
    stripe_total(1, 2)


def test_stripe_properly():
    assert stripe_total(0, 0) == 0
    assert stripe_total(1, 0) == 1
    assert stripe_total(0, 1) == 1
    assert stripe_total(-1, 1) == 0


def test_stripe_double():
    assert stripe_double(1, 2, 3) == 6


@covers(stripe_multiply)
def test_stripe_multiply():
    assert stripe_multiply(1, 2, 3) == 9
    assert stripe_multiply(2, 2, 3) == 12
    assert stripe_multiply(3, 2, 3) == 15
    assert 1 == 1
