from coverage_stats import covers
from inventory.warehouse.orders import orders_total, orders_double, orders_multiply


def test_orders_basic():
    orders_total(1, 2)


def test_orders_properly():
    assert orders_total(0, 0) == 0
    assert orders_total(1, 0) == 1
    assert orders_total(0, 1) == 1
    assert orders_total(-1, 1) == 0


def test_orders_double():
    assert orders_double(1, 2, 3) == 6


@covers(orders_multiply)
def test_orders_multiply():
    assert orders_multiply(1, 2, 3) == 9
    assert orders_multiply(2, 2, 3) == 12
    assert orders_multiply(3, 2, 3) == 15
    assert 1 == 1
