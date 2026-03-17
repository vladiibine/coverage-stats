from coverage_stats import covers
from users.profiles.privacy import privacy_total, privacy_double, privacy_multiply


def test_privacy_basic():
    privacy_total(1, 2)


def test_privacy_properly():
    assert privacy_total(0, 0) == 0
    assert privacy_total(1, 0) == 1
    assert privacy_total(0, 1) == 1
    assert privacy_total(-1, 1) == 0


def test_privacy_double():
    assert privacy_double(1, 2, 3) == 6


@covers(privacy_multiply)
def test_privacy_multiply():
    assert privacy_multiply(1, 2, 3) == 9
    assert privacy_multiply(2, 2, 3) == 12
    assert privacy_multiply(3, 2, 3) == 15
    assert 1 == 1
