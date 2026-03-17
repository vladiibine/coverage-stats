from coverage_stats import covers
from reporting.audit.logs import logs_total, logs_double, logs_multiply


def test_logs_basic():
    logs_total(1, 2)


def test_logs_properly():
    assert logs_total(0, 0) == 0
    assert logs_total(1, 0) == 1
    assert logs_total(0, 1) == 1
    assert logs_total(-1, 1) == 0


def test_logs_double():
    assert logs_double(1, 2, 3) == 6


@covers(logs_multiply)
def test_logs_multiply():
    assert logs_multiply(1, 2, 3) == 9
    assert logs_multiply(2, 2, 3) == 12
    assert logs_multiply(3, 2, 3) == 15
    assert 1 == 1
