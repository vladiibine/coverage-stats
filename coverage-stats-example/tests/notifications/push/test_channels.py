from coverage_stats import covers
from notifications.push.channels import channels_total, channels_double, channels_multiply


def test_channels_basic():
    channels_total(1, 2)


def test_channels_properly():
    assert channels_total(0, 0) == 0
    assert channels_total(1, 0) == 1
    assert channels_total(0, 1) == 1
    assert channels_total(-1, 1) == 0


def test_channels_double():
    assert channels_double(1, 2, 3) == 6


@covers(channels_multiply)
def test_channels_multiply():
    assert channels_multiply(1, 2, 3) == 9
    assert channels_multiply(2, 2, 3) == 12
    assert channels_multiply(3, 2, 3) == 15
    assert 1 == 1
