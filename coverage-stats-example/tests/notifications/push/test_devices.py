from coverage_stats import covers
from notifications.push.devices import devices_total, devices_double, devices_multiply


def test_devices_basic():
    devices_total(1, 2)


def test_devices_properly():
    assert devices_total(0, 0) == 0
    assert devices_total(1, 0) == 1
    assert devices_total(0, 1) == 1
    assert devices_total(-1, 1) == 0


def test_devices_double():
    assert devices_double(1, 2, 3) == 6


@covers(devices_multiply)
def test_devices_multiply():
    assert devices_multiply(1, 2, 3) == 9
    assert devices_multiply(2, 2, 3) == 12
    assert devices_multiply(3, 2, 3) == 15
    assert 1 == 1
