from coverage_stats import covers
from inventory.products.search import search_total, search_double, search_multiply


def test_search_basic():
    search_total(1, 2)


def test_search_properly():
    assert search_total(0, 0) == 0
    assert search_total(1, 0) == 1
    assert search_total(0, 1) == 1
    assert search_total(-1, 1) == 0


def test_search_double():
    assert search_double(1, 2, 3) == 6


@covers(search_multiply)
def test_search_multiply():
    assert search_multiply(1, 2, 3) == 9
    assert search_multiply(2, 2, 3) == 12
    assert search_multiply(3, 2, 3) == 15
    assert 1 == 1
