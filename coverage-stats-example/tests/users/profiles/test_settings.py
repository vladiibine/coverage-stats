from coverage_stats import covers
from users.profiles.settings import settings_total, settings_double, settings_multiply


def test_settings_basic():
    settings_total(1, 2)


def test_settings_properly():
    assert settings_total(0, 0) == 0
    assert settings_total(1, 0) == 1
    assert settings_total(0, 1) == 1
    assert settings_total(-1, 1) == 0


def test_settings_double():
    assert settings_double(1, 2, 3) == 6


@covers(settings_multiply)
def test_settings_multiply():
    assert settings_multiply(1, 2, 3) == 9
    assert settings_multiply(2, 2, 3) == 12
    assert settings_multiply(3, 2, 3) == 15
    assert 1 == 1
