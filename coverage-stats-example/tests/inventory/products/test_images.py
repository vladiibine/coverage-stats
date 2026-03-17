from coverage_stats import covers
from inventory.products.images import images_total, images_double, images_multiply


def test_images_basic():
    images_total(1, 2)


def test_images_properly():
    assert images_total(0, 0) == 0
    assert images_total(1, 0) == 1
    assert images_total(0, 1) == 1
    assert images_total(-1, 1) == 0


def test_images_double():
    assert images_double(1, 2, 3) == 6


@covers(images_multiply)
def test_images_multiply():
    assert images_multiply(1, 2, 3) == 9
    assert images_multiply(2, 2, 3) == 12
    assert images_multiply(3, 2, 3) == 15
    assert 1 == 1
