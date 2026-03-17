from coverage_stats import covers
from users.profiles.avatar import avatar_total, avatar_double, avatar_multiply


def test_avatar_basic():
    avatar_total(1, 2)


def test_avatar_properly():
    assert avatar_total(0, 0) == 0
    assert avatar_total(1, 0) == 1
    assert avatar_total(0, 1) == 1
    assert avatar_total(-1, 1) == 0


def test_avatar_double():
    assert avatar_double(1, 2, 3) == 6


@covers(avatar_multiply)
def test_avatar_multiply():
    assert avatar_multiply(1, 2, 3) == 9
    assert avatar_multiply(2, 2, 3) == 12
    assert avatar_multiply(3, 2, 3) == 15
    assert 1 == 1
