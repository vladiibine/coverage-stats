from coverage_stats import covers
from inventory.products.catalog import catalog_total, catalog_double, catalog_multiply


def test_catalog_basic():
    catalog_total(1, 2)


def test_catalog_properly():
    assert catalog_total(0, 0) == 0
    assert catalog_total(1, 0) == 1
    assert catalog_total(0, 1) == 1
    assert catalog_total(-1, 1) == 0


def test_catalog_double():
    assert catalog_double(1, 2, 3) == 6


@covers(catalog_multiply)
def test_catalog_multiply():
    assert catalog_multiply(1, 2, 3) == 9
    assert catalog_multiply(2, 2, 3) == 12
    assert catalog_multiply(3, 2, 3) == 15
    assert 1 == 1
