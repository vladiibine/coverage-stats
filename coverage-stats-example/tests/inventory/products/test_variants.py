from coverage_stats import covers
from inventory.products.variants import variants_total, variants_double, variants_multiply


def test_variants_basic():
    variants_total(1, 2)


def test_variants_properly():
    assert variants_total(0, 0) == 0
    assert variants_total(1, 0) == 1
    assert variants_total(0, 1) == 1
    assert variants_total(-1, 1) == 0


def test_variants_double():
    assert variants_double(1, 2, 3) == 6


@covers(variants_multiply)
def test_variants_multiply():
    assert variants_multiply(1, 2, 3) == 9
    assert variants_multiply(2, 2, 3) == 12
    assert variants_multiply(3, 2, 3) == 15
    assert 1 == 1
