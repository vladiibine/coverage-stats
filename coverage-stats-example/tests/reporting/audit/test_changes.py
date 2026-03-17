from coverage_stats import covers
from reporting.audit.changes import changes_total, changes_double, changes_multiply


def test_changes_basic():
    changes_total(1, 2)


def test_changes_properly():
    assert changes_total(0, 0) == 0
    assert changes_total(1, 0) == 1
    assert changes_total(0, 1) == 1
    assert changes_total(-1, 1) == 0


def test_changes_double():
    assert changes_double(1, 2, 3) == 6


@covers(changes_multiply)
def test_changes_multiply():
    assert changes_multiply(1, 2, 3) == 9
    assert changes_multiply(2, 2, 3) == 12
    assert changes_multiply(3, 2, 3) == 15
    assert 1 == 1
