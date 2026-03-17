from coverage_stats import covers
from inventory.warehouse.transfers import transfers_total, transfers_double, transfers_multiply


def test_transfers_basic():
    transfers_total(1, 2)


def test_transfers_properly():
    assert transfers_total(0, 0) == 0
    assert transfers_total(1, 0) == 1
    assert transfers_total(0, 1) == 1
    assert transfers_total(-1, 1) == 0


def test_transfers_double():
    assert transfers_double(1, 2, 3) == 6


@covers(transfers_multiply)
def test_transfers_multiply():
    assert transfers_multiply(1, 2, 3) == 9
    assert transfers_multiply(2, 2, 3) == 12
    assert transfers_multiply(3, 2, 3) == 15
    assert 1 == 1
