from coverage_stats import covers
from payments.billing.invoices import invoices_total, invoices_double, invoices_multiply


def test_invoices_basic():
    invoices_total(1, 2)


def test_invoices_properly():
    assert invoices_total(0, 0) == 0
    assert invoices_total(1, 0) == 1
    assert invoices_total(0, 1) == 1
    assert invoices_total(-1, 1) == 0


def test_invoices_double():
    assert invoices_double(1, 2, 3) == 6


@covers(invoices_multiply)
def test_invoices_multiply():
    assert invoices_multiply(1, 2, 3) == 9
    assert invoices_multiply(2, 2, 3) == 12
    assert invoices_multiply(3, 2, 3) == 15
    assert 1 == 1
