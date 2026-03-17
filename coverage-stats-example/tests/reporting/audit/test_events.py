from coverage_stats import covers
from reporting.audit.events import events_total, events_double, events_multiply


def test_events_basic():
    events_total(1, 2)


def test_events_properly():
    assert events_total(0, 0) == 0
    assert events_total(1, 0) == 1
    assert events_total(0, 1) == 1
    assert events_total(-1, 1) == 0


def test_events_double():
    assert events_double(1, 2, 3) == 6


@covers(events_multiply)
def test_events_multiply():
    assert events_multiply(1, 2, 3) == 9
    assert events_multiply(2, 2, 3) == 12
    assert events_multiply(3, 2, 3) == 15
    assert 1 == 1
