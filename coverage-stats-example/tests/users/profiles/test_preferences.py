from coverage_stats import covers
from users.profiles.preferences import preferences_total, preferences_double, preferences_multiply


def test_preferences_basic():
    preferences_total(1, 2)


def test_preferences_properly():
    assert preferences_total(0, 0) == 0
    assert preferences_total(1, 0) == 1
    assert preferences_total(0, 1) == 1
    assert preferences_total(-1, 1) == 0


def test_preferences_double():
    assert preferences_double(1, 2, 3) == 6


@covers(preferences_multiply)
def test_preferences_multiply():
    assert preferences_multiply(1, 2, 3) == 9
    assert preferences_multiply(2, 2, 3) == 12
    assert preferences_multiply(3, 2, 3) == 15
    assert 1 == 1
