# coverage-stats

A pytest plugin that tracks deliberate vs incidental line coverage per test.
It works like a pytest plugin, that reports (in a way similar to how coverage.py does it):
1. The number of asserts that were executed in tests that covered each of the lines reported
2. The number of times each line was executed
3. It distinguishes between incidental coverage and deliberate coverage. Deliberate coverage means that a test was marked with `@covers(...)` so we can know exactly what lines in the app were tested on purpose in that test. Incidental coverage means the line was covered in tests, but not deliberately

## Install

```bash
pip install coverage-stats
```

## Usage

```bash
pytest --coverage-stats

# then open in the browser ./coverage-stats-report/index.html
```

Mark which lines a test deliberately covers using the `covers` decorator:

```python
from coverage_stats import covers

@covers("mymodule.MyClass.my_method")
def test_my_method():
    ...
```

## HTML Report

Generate a self-contained HTML report:

```bash
pytest --coverage-stats --coverage-stats-format=html
```

The report is written to `coverage-stats-report/` by default. To change the output directory:

```bash
pytest --coverage-stats --coverage-stats-format=html --coverage-stats-output=reports/
```

The report includes a folder-collapsible index with per-file summary metrics, and a per-file page showing line-level deliberate vs incidental execution counts and assert density.

### Index page columns

Each row represents one file or folder. Columns are toggleable via checkboxes above the table; the default visibility is noted below.

| Column | Default | Description |
|--------|---------|-------------|
| Stmts | visible | Total number of statements + branches tracked in the file or folder. |
| Total % | visible | Percentage of statements + branches covered by any test (deliberate or incidental). Files with nothing to cover (e.g. empty `__init__.py`) show 100%. |
| Deliberate % | visible | Percentage of statements + branches covered by at least one test that explicitly declares coverage via `@covers(...)`. |
| Incidental % | visible | Percentage of statements + branches covered incidentally — executed by tests, but not via a `@covers` declaration. |
| Del. Covered | hidden | Raw count of statements + branches covered deliberately. Colored using the same level as the Deliberate % column. |
| Inc. Covered | hidden | Raw count of statements + branches covered incidentally. Colored using the same level as the Incidental % column. |
| Inc. Asserts | hidden | Total number of assert statements executed during incidental coverage of this file or folder. |
| Del. Asserts | hidden | Total number of assert statements executed during deliberate coverage of this file or folder. |
| Inc. Assert Density | hidden | Incidental assert count divided by total statements + branches. A higher value means more assertions are observing each line incidentally. |
| Del. Assert Density | hidden | Deliberate assert count divided by total statements + branches. A higher value means more targeted assertions are exercising each line. |

Percentage columns are colored on a 10-level red → green scale (0–9%, 10–19%, …, 90–100%). Assert count and density columns are colored relative to the maximum value in the current report (divided into up to 10 equal buckets).

### File report columns

Each row represents one source line. Columns are toggleable via checkboxes above the table.

| Column | Default | Description                                                                                                      |
|--------|---------|------------------------------------------------------------------------------------------------------------------|
| Inc. Executions | visible | Number of times the line was executed by incidental tests.                                                       |
| Del. Executions | visible | Number of times the line was executed by deliberate tests (tests with a matching `@covers` declaration).         |
| Inc. Asserts | visible | Number of assert statements executed in all of the tests that ran when the line was executed incidentally.       |
| Del. Asserts | visible | Number of assert statements executed in all of the tests that ran when the line was executed incidentally.        |
| Inc. Tests | visible | Number of distinct incidental tests that executed this line.                                                     |
| Del. Tests | visible | Number of distinct deliberate tests that executed this line.                                                     |

Row background colors: green = covered deliberately, yellow = covered only incidentally, orange = partially covered (some branches missed), red = not covered at all.

### Scoping profiling to specific directories

By default all non-stdlib, non-site-packages files are profiled. To limit profiling to specific source directories, set `coverage_stats_source` in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
coverage_stats_source = "src"
```

Multiple directories are space-separated:

```toml
[tool.pytest.ini_options]
coverage_stats_source = "src/mypackage src/otherpackage"
```

### Other output formats

JSON and CSV outputs are also supported:

```bash
pytest --coverage-stats --coverage-stats-format=json,csv --coverage-stats-output=reports/
```

**JSON** (`coverage-stats.json`) — machine-readable, suitable for CI dashboards and trend analysis.

**CSV** (`coverage-stats.csv`) — one row per line, columns: `file`, `lineno`, `incidental_executions`, `deliberate_executions`, `incidental_asserts`, `deliberate_asserts`.

> **Note:** Assert density metrics require pytest's default assertion rewriting. Running with `--assert=plain` disables assert counting.

## Development

### Running the test suite

Install [nox](https://nox.thea.codes) (once):

```bash
uv tool install nox
```

And then here are examples of how you could run the tests, linting and type checking
```bash
# tests (all Python versions), mypy, ruff
nox

# only the tests (all Python versions)
nox -s tests

# Only the tests, python 3.12
nox -s "tests-3.12"
```


Individual sessions:

| Session | What it runs |
|---------|-------------|
| `tests` | pytest across Python 3.9–3.14 |
| `mypy`  | mypy strict type-checking |
| `lint`  | ruff |

### Pre-commit hook

A pre-commit hook runs the full `nox` suite before every commit and blocks it if any check fails. To enable it, first install nox and pre-commit (once):

```bash
uv tool install nox
uv tool install pre-commit
```

Then install the hook into your local clone (once):

```bash
pre-commit install
```

From that point on, every `git commit` automatically runs all nox sessions. To skip the hook for a single commit (e.g. a work-in-progress), use `git commit --no-verify`.

> **Tip:** The full matrix (Python 3.9–3.14 + mypy + lint) can be slow locally. To run just one Python version instead, edit the `entry` line in `.pre-commit-config.yaml` to `nox -s "tests-3.12" mypy lint`.

### Type checking

Run mypy directly (without nox):

```bash
pip install -e ".[dev]"
mypy src/
```

mypy is configured in `pyproject.toml` under `[tool.mypy]` with strict mode enabled.

## Publishing
```bash
# 1. build
uv run python -m build

# 2. upload
uv run twine upload dist/*
```