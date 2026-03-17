from coverage_stats import covers
from notifications.push.batch import batch_total, batch_double, batch_multiply


def test_batch_basic():
    batch_total(1, 2)


def test_batch_properly():
    assert batch_total(0, 0) == 0
    assert batch_total(1, 0) == 1
    assert batch_total(0, 1) == 1
    assert batch_total(-1, 1) == 0


def test_batch_double():
    assert batch_double(1, 2, 3) == 6


@covers(batch_multiply)
def test_batch_multiply():
    assert batch_multiply(1, 2, 3) == 9
    assert batch_multiply(2, 2, 3) == 12
    assert batch_multiply(3, 2, 3) == 15
    assert 1 == 1
