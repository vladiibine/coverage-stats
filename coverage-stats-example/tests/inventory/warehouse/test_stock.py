from coverage_stats import covers
from inventory.warehouse.stock import stock_total, stock_double, stock_multiply


def test_stock_basic():
    stock_total(1, 2)


def test_stock_properly():
    assert stock_total(0, 0) == 0
    assert stock_total(1, 0) == 1
    assert stock_total(0, 1) == 1
    assert stock_total(-1, 1) == 0


def test_stock_double():
    assert stock_double(1, 2, 3) == 6


@covers(stock_multiply)
def test_stock_multiply():
    assert stock_multiply(1, 2, 3) == 9
    assert stock_multiply(2, 2, 3) == 12
    assert stock_multiply(3, 2, 3) == 15
    assert 1 == 1
