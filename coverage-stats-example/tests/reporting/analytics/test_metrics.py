from coverage_stats import covers
from reporting.analytics.metrics import metrics_total, metrics_double, metrics_multiply


def test_metrics_basic():
    metrics_total(1, 2)


def test_metrics_properly():
    assert metrics_total(0, 0) == 0
    assert metrics_total(1, 0) == 1
    assert metrics_total(0, 1) == 1
    assert metrics_total(-1, 1) == 0


def test_metrics_double():
    assert metrics_double(1, 2, 3) == 6


@covers(metrics_multiply)
def test_metrics_multiply():
    assert metrics_multiply(1, 2, 3) == 9
    assert metrics_multiply(2, 2, 3) == 12
    assert metrics_multiply(3, 2, 3) == 15
    assert 1 == 1
