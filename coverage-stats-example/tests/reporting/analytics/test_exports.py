from coverage_stats import covers
from reporting.analytics.exports import exports_total, exports_double, exports_multiply


def test_exports_basic():
    exports_total(1, 2)


def test_exports_properly():
    assert exports_total(0, 0) == 0
    assert exports_total(1, 0) == 1
    assert exports_total(0, 1) == 1
    assert exports_total(-1, 1) == 0


def test_exports_double():
    assert exports_double(1, 2, 3) == 6


@covers(exports_multiply)
def test_exports_multiply():
    assert exports_multiply(1, 2, 3) == 9
    assert exports_multiply(2, 2, 3) == 12
    assert exports_multiply(3, 2, 3) == 15
    assert 1 == 1
