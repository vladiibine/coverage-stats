from coverage_stats import covers
from notifications.push.messages import messages_total, messages_double, messages_multiply


def test_messages_basic():
    messages_total(1, 2)


def test_messages_properly():
    assert messages_total(0, 0) == 0
    assert messages_total(1, 0) == 1
    assert messages_total(0, 1) == 1
    assert messages_total(-1, 1) == 0


def test_messages_double():
    assert messages_double(1, 2, 3) == 6


@covers(messages_multiply)
def test_messages_multiply():
    assert messages_multiply(1, 2, 3) == 9
    assert messages_multiply(2, 2, 3) == 12
    assert messages_multiply(3, 2, 3) == 15
    assert 1 == 1
