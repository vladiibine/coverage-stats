from coverage_stats import covers
from asdf import (
    double_sum, multiply_sum, foo_sum, weird_corner_cases_1_while_loop_, weird_corner_cases_2_for_loop,
    weird_case_multiple_statements_on_one_line, weird_corner_cases_4_with_,
    weird_corner_cases_5_match,
)


def test_badly_foo_sum():
    foo_sum(1, 2)


def test_properly_foo_sum():
    assert foo_sum(0, 0) == 0
    assert foo_sum(1, 0) == 1
    assert foo_sum(0, 1) == 1
    assert foo_sum(-1, 1) == 0


def test_double_sum_1():
    assert double_sum(1, 2, 3) == 6


@covers(multiply_sum)
def test_multiply_sum():
    assert multiply_sum(1, 2, 3) == 9
    assert multiply_sum(2, 2, 3) == 12
    assert multiply_sum(3, 2, 3) == 15
    assert 1 == 1


@covers(weird_corner_cases_1_while_loop_)
def test_weird_corner_cases_1():
    weird_corner_cases_1_while_loop_([1, 2, 3], 2)


def test_weird_corner_cases_2():
    assert weird_corner_cases_2_for_loop([1, 3, ], []) == 15

def test_weird_case_multiple_statements_on_one_line():
    assert weird_case_multiple_statements_on_one_line(2, 0) == 12


@covers(weird_corner_cases_4_with_)
def test_weird_corner_cases_4():
    # Both paths: exception suppressed (a=0) and normal (a=2)
    assert weird_corner_cases_4_with_(0) == 0
    assert weird_corner_cases_4_with_(2) == 5


def test_weird_corner_cases_5():
    # Only case 1 — case 2 and wildcard intentionally not tested
    assert weird_corner_cases_5_match(1) == "one"