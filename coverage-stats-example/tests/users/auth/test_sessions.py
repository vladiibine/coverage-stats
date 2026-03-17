from coverage_stats import covers
from users.auth.sessions import sessions_total, sessions_double, sessions_multiply


def test_sessions_basic():
    sessions_total(1, 2)


def test_sessions_properly():
    assert sessions_total(0, 0) == 0
    assert sessions_total(1, 0) == 1
    assert sessions_total(0, 1) == 1
    assert sessions_total(-1, 1) == 0


def test_sessions_double():
    assert sessions_double(1, 2, 3) == 6


@covers(sessions_multiply)
def test_sessions_multiply():
    assert sessions_multiply(1, 2, 3) == 9
    assert sessions_multiply(2, 2, 3) == 12
    assert sessions_multiply(3, 2, 3) == 15
    assert 1 == 1
