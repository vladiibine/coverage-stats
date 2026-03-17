from coverage_stats import covers
from inventory.warehouse.locations import locations_total, locations_double, locations_multiply


def test_locations_basic():
    locations_total(1, 2)


def test_locations_properly():
    assert locations_total(0, 0) == 0
    assert locations_total(1, 0) == 1
    assert locations_total(0, 1) == 1
    assert locations_total(-1, 1) == 0


def test_locations_double():
    assert locations_double(1, 2, 3) == 6


@covers(locations_multiply)
def test_locations_multiply():
    assert locations_multiply(1, 2, 3) == 9
    assert locations_multiply(2, 2, 3) == 12
    assert locations_multiply(3, 2, 3) == 15
    assert 1 == 1
