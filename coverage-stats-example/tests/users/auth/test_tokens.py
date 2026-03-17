from coverage_stats import covers
from users.auth.tokens import tokens_total, tokens_double, tokens_multiply


def test_tokens_basic():
    tokens_total(1, 2)


def test_tokens_properly():
    assert tokens_total(0, 0) == 0
    assert tokens_total(1, 0) == 1
    assert tokens_total(0, 1) == 1
    assert tokens_total(-1, 1) == 0


def test_tokens_double():
    assert tokens_double(1, 2, 3) == 6


@covers(tokens_multiply)
def test_tokens_multiply():
    assert tokens_multiply(1, 2, 3) == 9
    assert tokens_multiply(2, 2, 3) == 12
    assert tokens_multiply(3, 2, 3) == 15
    assert 1 == 1
