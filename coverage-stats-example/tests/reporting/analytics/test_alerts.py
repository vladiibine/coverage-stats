from coverage_stats import covers
from reporting.analytics.alerts import alerts_total, alerts_double, alerts_multiply


def test_alerts_basic():
    alerts_total(1, 2)


def test_alerts_properly():
    assert alerts_total(0, 0) == 0
    assert alerts_total(1, 0) == 1
    assert alerts_total(0, 1) == 1
    assert alerts_total(-1, 1) == 0


def test_alerts_double():
    assert alerts_double(1, 2, 3) == 6


@covers(alerts_multiply)
def test_alerts_multiply():
    assert alerts_multiply(1, 2, 3) == 9
    assert alerts_multiply(2, 2, 3) == 12
    assert alerts_multiply(3, 2, 3) == 15
    assert 1 == 1
