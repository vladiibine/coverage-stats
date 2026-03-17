from coverage_stats import covers
from notifications.email.bounce import bounce_total, bounce_double, bounce_multiply


def test_bounce_basic():
    bounce_total(1, 2)


def test_bounce_properly():
    assert bounce_total(0, 0) == 0
    assert bounce_total(1, 0) == 1
    assert bounce_total(0, 1) == 1
    assert bounce_total(-1, 1) == 0


def test_bounce_double():
    assert bounce_double(1, 2, 3) == 6


@covers(bounce_multiply)
def test_bounce_multiply():
    assert bounce_multiply(1, 2, 3) == 9
    assert bounce_multiply(2, 2, 3) == 12
    assert bounce_multiply(3, 2, 3) == 15
    assert 1 == 1
