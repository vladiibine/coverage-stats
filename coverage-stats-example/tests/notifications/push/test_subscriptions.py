from coverage_stats import covers
from notifications.push.subscriptions import subscriptions_total, subscriptions_double, subscriptions_multiply


def test_subscriptions_basic():
    subscriptions_total(1, 2)


def test_subscriptions_properly():
    assert subscriptions_total(0, 0) == 0
    assert subscriptions_total(1, 0) == 1
    assert subscriptions_total(0, 1) == 1
    assert subscriptions_total(-1, 1) == 0


def test_subscriptions_double():
    assert subscriptions_double(1, 2, 3) == 6


@covers(subscriptions_multiply)
def test_subscriptions_multiply():
    assert subscriptions_multiply(1, 2, 3) == 9
    assert subscriptions_multiply(2, 2, 3) == 12
    assert subscriptions_multiply(3, 2, 3) == 15
    assert 1 == 1
