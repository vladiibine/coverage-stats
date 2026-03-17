from coverage_stats import covers
from asdf import double_sum, multiply_sum, foo_sum

def test_badly_foo_sum():
   foo_sum(1,2)

def test_properly_foo_sum():
  assert foo_sum(0,0) == 0
  assert foo_sum(1,0) == 1
  assert foo_sum(0,1) == 1
  assert foo_sum(-1,1) == 0

def test_double_sum_1():
   assert double_sum(1, 2, 3) == 6

@covers(multiply_sum)
def test_multiply_sum():
   assert multiply_sum(1, 2, 3) == 9
   assert multiply_sum(2, 2, 3) == 12
   assert multiply_sum(3, 2, 3) == 15
   assert 1 == 1
