from coverage_stats import covers
from payments.billing.refunds import refunds_total, refunds_double, refunds_multiply


def test_refunds_basic():
    refunds_total(1, 2)


def test_refunds_properly():
    assert refunds_total(0, 0) == 0
    assert refunds_total(1, 0) == 1
    assert refunds_total(0, 1) == 1
    assert refunds_total(-1, 1) == 0


def test_refunds_double():
    assert refunds_double(1, 2, 3) == 6


@covers(refunds_multiply)
def test_refunds_multiply():
    assert refunds_multiply(1, 2, 3) == 9
    assert refunds_multiply(2, 2, 3) == 12
    assert refunds_multiply(3, 2, 3) == 15
    assert 1 == 1
