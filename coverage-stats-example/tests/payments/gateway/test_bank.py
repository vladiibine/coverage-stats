from coverage_stats import covers
from payments.gateway.bank import bank_total, bank_double, bank_multiply


def test_bank_basic():
    bank_total(1, 2)


def test_bank_properly():
    assert bank_total(0, 0) == 0
    assert bank_total(1, 0) == 1
    assert bank_total(0, 1) == 1
    assert bank_total(-1, 1) == 0


def test_bank_double():
    assert bank_double(1, 2, 3) == 6


@covers(bank_multiply)
def test_bank_multiply():
    assert bank_multiply(1, 2, 3) == 9
    assert bank_multiply(2, 2, 3) == 12
    assert bank_multiply(3, 2, 3) == 15
    assert 1 == 1
