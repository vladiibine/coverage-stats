from coverage_stats import covers
from asdf2 import ( foo_sum2
)

def test_foo_sum2():
    assert foo_sum2(1, 2) == 3
    assert foo_sum2(1, 2) == 3

def test_foo_sum2_2():
    # assert foo_sum2(1, 2) == 3
    assert foo_sum2(1, 2) == 3

@covers(foo_sum2)
def test_foo_sum2_deliberately():
    assert foo_sum2(10, 20) == 30