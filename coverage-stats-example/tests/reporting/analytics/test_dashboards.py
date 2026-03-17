from coverage_stats import covers
from reporting.analytics.dashboards import dashboards_total, dashboards_double, dashboards_multiply


def test_dashboards_basic():
    dashboards_total(1, 2)


def test_dashboards_properly():
    assert dashboards_total(0, 0) == 0
    assert dashboards_total(1, 0) == 1
    assert dashboards_total(0, 1) == 1
    assert dashboards_total(-1, 1) == 0


def test_dashboards_double():
    assert dashboards_double(1, 2, 3) == 6


@covers(dashboards_multiply)
def test_dashboards_multiply():
    assert dashboards_multiply(1, 2, 3) == 9
    assert dashboards_multiply(2, 2, 3) == 12
    assert dashboards_multiply(3, 2, 3) == 15
    assert 1 == 1
