from coverage_stats import covers
from users.auth.oauth import oauth_total, oauth_double, oauth_multiply


def test_oauth_basic():
    oauth_total(1, 2)


def test_oauth_properly():
    assert oauth_total(0, 0) == 0
    assert oauth_total(1, 0) == 1
    assert oauth_total(0, 1) == 1
    assert oauth_total(-1, 1) == 0


def test_oauth_double():
    assert oauth_double(1, 2, 3) == 6


@covers(oauth_multiply)
def test_oauth_multiply():
    assert oauth_multiply(1, 2, 3) == 9
    assert oauth_multiply(2, 2, 3) == 12
    assert oauth_multiply(3, 2, 3) == 15
    assert 1 == 1
