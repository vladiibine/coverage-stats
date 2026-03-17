from coverage_stats import covers
from reporting.audit.access import access_total, access_double, access_multiply


def test_access_basic():
    access_total(1, 2)


def test_access_properly():
    assert access_total(0, 0) == 0
    assert access_total(1, 0) == 1
    assert access_total(0, 1) == 1
    assert access_total(-1, 1) == 0


def test_access_double():
    assert access_double(1, 2, 3) == 6


@covers(access_multiply)
def test_access_multiply():
    assert access_multiply(1, 2, 3) == 9
    assert access_multiply(2, 2, 3) == 12
    assert access_multiply(3, 2, 3) == 15
    assert 1 == 1
