from coverage_stats import covers
from notifications.email.tracking import tracking_total, tracking_double, tracking_multiply


def test_tracking_basic():
    tracking_total(1, 2)


def test_tracking_properly():
    assert tracking_total(0, 0) == 0
    assert tracking_total(1, 0) == 1
    assert tracking_total(0, 1) == 1
    assert tracking_total(-1, 1) == 0


def test_tracking_double():
    assert tracking_double(1, 2, 3) == 6


@covers(tracking_multiply)
def test_tracking_multiply():
    assert tracking_multiply(1, 2, 3) == 9
    assert tracking_multiply(2, 2, 3) == 12
    assert tracking_multiply(3, 2, 3) == 15
    assert 1 == 1
