# coverage-stats

Enhanced coverage reporting for pytest. Instead of the binary "covered / not covered", coverage-stats shows **how many times each line was executed** and distinguishes between two kinds of hits:

| Hit type | Meaning |
|---|---|
| **Direct** | The line was executed by a test that explicitly declares it covers this function/class/module via `@covers` |
| **Incidental** | The line was executed by a test that didn't declare it — a side effect of running other code |

This helps you answer questions like:
- *Is this function actually tested directly, or only touched incidentally?*
- *How many of my tests are actually focused on this class?*

---

## Installation

```bash
pip install coverage-stats
```

This installs two things:
- A **pytest plugin** (auto-activated) that tracks which tests cover what
- A **CLI tool** (`coverage-stats`) for generating the enhanced HTML report

---

## Quickstart

### 1. Mark your tests with `@covers`

```python
from coverage_stats import covers
from myapp.billing import Invoice, calculate_total

@covers(Invoice.apply_discount)
def test_discount_reduces_total():
    inv = Invoice(total=100)
    inv.apply_discount(10)
    assert inv.total == 90

@covers(calculate_total)
def test_calculate_total_with_tax():
    assert calculate_total(items=[10, 20], tax=0.1) == 33.0

# Tests without @covers still run and their hits are counted as incidental
def test_full_checkout_flow():
    # touches Invoice, calculate_total, and more — all incidental hits
    ...
```

You can declare multiple targets on one test:

```python
@covers(Invoice, calculate_total)
def test_invoice_total():
    ...
```

Targets can be functions, methods, classes, modules, or strings:

```python
@covers(Invoice.apply_discount)          # method
@covers(Invoice)                         # entire class
@covers(myapp.billing)                   # entire module
@covers("myapp.billing.calculate_total") # string form
```

### 2. Run pytest with coverage

```bash
pytest --cov=src --cov-context=test
```

The `--cov-context=test` flag tells coverage.py to record which test caused each line hit. coverage-stats depends on this.

### 3. Generate the report

```bash
coverage-stats html
```

Open `htmlcov_stats/index.html` in your browser.

---

## HTML report

Each line in the report shows three pieces of information:

```
 42  |  2 d  1 i  |      return a + b
```

- `2 d` — 2 direct hits (from tests that `@covers` this function)
- `1 i` — 1 incidental hit (from tests that ran this line without declaring it)

**Color coding:**

| Color | Meaning |
|---|---|
| Green | Line has at least one direct hit |
| Yellow | Line has only incidental hits |
| Red | Executable line with zero hits (not covered at all) |
| White | Non-executable line (comments, blank lines, etc.) |

---

## CLI reference

```
usage: coverage-stats html [options]

Options:
  --data-file PATH   Path to the .coverage data file (default: .coverage)
  --meta-file PATH   Path to coverage-stats metadata (default: .coverage-stats-meta.json)
  --output DIR       Output directory for the HTML report (default: htmlcov_stats)
```

Examples:

```bash
# Use defaults
coverage-stats html

# Custom paths
coverage-stats html --data-file .coverage.myproject --output reports/coverage
```

---

## How it works

When pytest runs:
1. The coverage-stats pytest plugin records which tests have `@covers` declarations and saves them to `.coverage-stats-meta.json`.
2. `coverage.py` (via `--cov-context=test`) records which test caused each line hit, storing per-test context data in the `.coverage` file.

When you run `coverage-stats html`:
1. The `.coverage` file is read to get per-line hit counts broken down by test.
2. The metadata file is read to know which tests have `@covers` declarations and what they declare.
3. Each source file is AST-analyzed to map line numbers to their enclosing function/class scope.
4. For every line hit, the plugin checks whether the hitting test declared `@covers` for that line's enclosing scope. If yes → direct hit. If no → incidental hit.
5. An HTML report is generated with the counts.

---

## Tips

**Don't feel pressured to `@covers` everything.** Tests without `@covers` still contribute to coverage — their hits just show up as incidental. The decorator is opt-in and most useful for unit tests that have a clear, specific target.

**Incidental hits aren't bad.** High incidental counts on a function can mean it's well-exercised by integration tests. The distinction is about *intent*, not quality.

**`@covers` doesn't change what gets tested.** It's purely a metadata annotation. It has no effect on how your test runs.
