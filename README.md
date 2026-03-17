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

### Type checking

Install dev dependencies and run mypy:

```bash
pip install -e ".[dev]"
mypy
```

mypy is configured in `pyproject.toml` under `[tool.mypy]` with strict mode enabled.
