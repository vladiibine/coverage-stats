from coverage_stats import covers
from notifications.email.sender import sender_total, sender_double, sender_multiply


def test_sender_basic():
    sender_total(1, 2)


def test_sender_properly():
    assert sender_total(0, 0) == 0
    assert sender_total(1, 0) == 1
    assert sender_total(0, 1) == 1
    assert sender_total(-1, 1) == 0


def test_sender_double():
    assert sender_double(1, 2, 3) == 6


@covers(sender_multiply)
def test_sender_multiply():
    assert sender_multiply(1, 2, 3) == 9
    assert sender_multiply(2, 2, 3) == 12
    assert sender_multiply(3, 2, 3) == 15
    assert 1 == 1
