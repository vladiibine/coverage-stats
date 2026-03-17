from coverage_stats import covers
from inventory.warehouse.suppliers import suppliers_total, suppliers_double, suppliers_multiply


def test_suppliers_basic():
    suppliers_total(1, 2)


def test_suppliers_properly():
    assert suppliers_total(0, 0) == 0
    assert suppliers_total(1, 0) == 1
    assert suppliers_total(0, 1) == 1
    assert suppliers_total(-1, 1) == 0


def test_suppliers_double():
    assert suppliers_double(1, 2, 3) == 6


@covers(suppliers_multiply)
def test_suppliers_multiply():
    assert suppliers_multiply(1, 2, 3) == 9
    assert suppliers_multiply(2, 2, 3) == 12
    assert suppliers_multiply(3, 2, 3) == 15
    assert 1 == 1
