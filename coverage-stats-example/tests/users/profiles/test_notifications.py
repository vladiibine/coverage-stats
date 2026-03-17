from coverage_stats import covers
from users.profiles.notifications import notifications_total, notifications_double, notifications_multiply


def test_notifications_basic():
    notifications_total(1, 2)


def test_notifications_properly():
    assert notifications_total(0, 0) == 0
    assert notifications_total(1, 0) == 1
    assert notifications_total(0, 1) == 1
    assert notifications_total(-1, 1) == 0


def test_notifications_double():
    assert notifications_double(1, 2, 3) == 6


@covers(notifications_multiply)
def test_notifications_multiply():
    assert notifications_multiply(1, 2, 3) == 9
    assert notifications_multiply(2, 2, 3) == 12
    assert notifications_multiply(3, 2, 3) == 15
    assert 1 == 1
