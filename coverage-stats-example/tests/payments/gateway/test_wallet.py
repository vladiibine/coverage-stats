from coverage_stats import covers
from payments.gateway.wallet import wallet_total, wallet_double, wallet_multiply


def test_wallet_basic():
    wallet_total(1, 2)


def test_wallet_properly():
    assert wallet_total(0, 0) == 0
    assert wallet_total(1, 0) == 1
    assert wallet_total(0, 1) == 1
    assert wallet_total(-1, 1) == 0


def test_wallet_double():
    assert wallet_double(1, 2, 3) == 6


@covers(wallet_multiply)
def test_wallet_multiply():
    assert wallet_multiply(1, 2, 3) == 9
    assert wallet_multiply(2, 2, 3) == 12
    assert wallet_multiply(3, 2, 3) == 15
    assert 1 == 1
