from coverage_stats import covers
from notifications.email.queue_mgr import queue_mgr_total, queue_mgr_double, queue_mgr_multiply


def test_queue_mgr_basic():
    queue_mgr_total(1, 2)


def test_queue_mgr_properly():
    assert queue_mgr_total(0, 0) == 0
    assert queue_mgr_total(1, 0) == 1
    assert queue_mgr_total(0, 1) == 1
    assert queue_mgr_total(-1, 1) == 0


def test_queue_mgr_double():
    assert queue_mgr_double(1, 2, 3) == 6


@covers(queue_mgr_multiply)
def test_queue_mgr_multiply():
    assert queue_mgr_multiply(1, 2, 3) == 9
    assert queue_mgr_multiply(2, 2, 3) == 12
    assert queue_mgr_multiply(3, 2, 3) == 15
    assert 1 == 1
