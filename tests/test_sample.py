"""
Example tests demonstrating @covers usage.

Run with:
    pytest --cov=tests/sample_module tests/test_sample.py
    coverage-stats html
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from coverage_stats import covers
from tests.sample_module import Calculator, standalone_function


# --- Tests that explicitly declare what they cover ---

@covers(Calculator.add)
def test_add_positive():
    calc = Calculator()
    assert calc.add(1, 2) == 3


@covers(Calculator.add)
def test_add_negative():
    calc = Calculator()
    assert calc.add(-1, -2) == -3


@covers(Calculator.subtract)
def test_subtract():
    calc = Calculator()
    assert calc.subtract(5, 3) == 2


@covers(standalone_function)
def test_standalone_positive():
    assert standalone_function(5) == 10


@covers(standalone_function)
def test_standalone_zero():
    assert standalone_function(0) == 0


# --- Tests that exercise code WITHOUT @covers (incidental coverage) ---

def test_multiply_no_covers():
    """This test covers multiply but doesn't declare it — incidental hit."""
    calc = Calculator()
    assert calc.multiply(3, 4) == 12


def test_integration_no_covers():
    """Uses add and standalone_function — both get incidental hits."""
    calc = Calculator()
    result = calc.add(standalone_function(2), 1)
    assert result == 5
