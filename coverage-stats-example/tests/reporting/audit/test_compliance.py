from coverage_stats import covers
from reporting.audit.compliance import compliance_total, compliance_double, compliance_multiply


def test_compliance_basic():
    compliance_total(1, 2)


def test_compliance_properly():
    assert compliance_total(0, 0) == 0
    assert compliance_total(1, 0) == 1
    assert compliance_total(0, 1) == 1
    assert compliance_total(-1, 1) == 0


def test_compliance_double():
    assert compliance_double(1, 2, 3) == 6


@covers(compliance_multiply)
def test_compliance_multiply():
    assert compliance_multiply(1, 2, 3) == 9
    assert compliance_multiply(2, 2, 3) == 12
    assert compliance_multiply(3, 2, 3) == 15
    assert 1 == 1
