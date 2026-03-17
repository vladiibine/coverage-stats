from coverage_stats import covers
from users.auth.passwords import passwords_total, passwords_double, passwords_multiply


def test_passwords_basic():
    passwords_total(1, 2)


def test_passwords_properly():
    assert passwords_total(0, 0) == 0
    assert passwords_total(1, 0) == 1
    assert passwords_total(0, 1) == 1
    assert passwords_total(-1, 1) == 0


def test_passwords_double():
    assert passwords_double(1, 2, 3) == 6


@covers(passwords_multiply)
def test_passwords_multiply():
    assert passwords_multiply(1, 2, 3) == 9
    assert passwords_multiply(2, 2, 3) == 12
    assert passwords_multiply(3, 2, 3) == 15
    assert 1 == 1
