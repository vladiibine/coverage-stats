from coverage_stats import covers
from users.auth.login import login_total, login_double, login_multiply


def test_login_basic():
    login_total(1, 2)


def test_login_properly():
    assert login_total(0, 0) == 0
    assert login_total(1, 0) == 1
    assert login_total(0, 1) == 1
    assert login_total(-1, 1) == 0


def test_login_double():
    assert login_double(1, 2, 3) == 6


@covers(login_multiply)
def test_login_multiply():
    assert login_multiply(1, 2, 3) == 9
    assert login_multiply(2, 2, 3) == 12
    assert login_multiply(3, 2, 3) == 15
    assert 1 == 1
