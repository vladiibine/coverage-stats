from coverage_stats import covers
from payments.gateway.crypto import crypto_total, crypto_double, crypto_multiply


def test_crypto_basic():
    crypto_total(1, 2)


def test_crypto_properly():
    assert crypto_total(0, 0) == 0
    assert crypto_total(1, 0) == 1
    assert crypto_total(0, 1) == 1
    assert crypto_total(-1, 1) == 0


def test_crypto_double():
    assert crypto_double(1, 2, 3) == 6


@covers(crypto_multiply)
def test_crypto_multiply():
    assert crypto_multiply(1, 2, 3) == 9
    assert crypto_multiply(2, 2, 3) == 12
    assert crypto_multiply(3, 2, 3) == 15
    assert 1 == 1
