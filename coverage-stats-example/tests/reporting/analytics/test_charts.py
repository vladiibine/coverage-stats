from coverage_stats import covers
from reporting.analytics.charts import charts_total, charts_double, charts_multiply


def test_charts_basic():
    charts_total(1, 2)


def test_charts_properly():
    assert charts_total(0, 0) == 0
    assert charts_total(1, 0) == 1
    assert charts_total(0, 1) == 1
    assert charts_total(-1, 1) == 0


def test_charts_double():
    assert charts_double(1, 2, 3) == 6


@covers(charts_multiply)
def test_charts_multiply():
    assert charts_multiply(1, 2, 3) == 9
    assert charts_multiply(2, 2, 3) == 12
    assert charts_multiply(3, 2, 3) == 15
    assert 1 == 1
