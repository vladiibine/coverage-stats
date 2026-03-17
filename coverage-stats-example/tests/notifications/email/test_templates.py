from coverage_stats import covers
from notifications.email.templates import templates_total, templates_double, templates_multiply


def test_templates_basic():
    templates_total(1, 2)


def test_templates_properly():
    assert templates_total(0, 0) == 0
    assert templates_total(1, 0) == 1
    assert templates_total(0, 1) == 1
    assert templates_total(-1, 1) == 0


def test_templates_double():
    assert templates_double(1, 2, 3) == 6


@covers(templates_multiply)
def test_templates_multiply():
    assert templates_multiply(1, 2, 3) == 9
    assert templates_multiply(2, 2, 3) == 12
    assert templates_multiply(3, 2, 3) == 15
    assert 1 == 1
