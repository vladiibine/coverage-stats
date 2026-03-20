# coverage-stats-example

A self-contained example project that demonstrates the `coverage-stats` pytest plugin
alongside standard `coverage.py`, so you can compare their HTML outputs side by side.

## Setup

From this directory, install dependencies with `uv`:

```bash
uv sync --extra dev
```

This installs `pytest`, `coverage`, `pytest-cov`, and the `coverage-stats` plugin
(sourced from the parent repo via the workspace).

## Running coverage-stats

The `coverage-stats` plugin is activated with `--coverage-stats` and produces its own
HTML report in `coverage-stats-report/`:

```bash
uv run pytest --coverage-stats --coverage-stats-format html
```

Open `coverage-stats-report/index.html` in a browser to see the result.

## Running coverage.py

Standard `coverage.py` branch coverage with an HTML report in `html-cov/`:

```bash
uv run pytest --cov=src --cov-branch --cov-report=html:html-cov
```

Open `html-cov/index.html` in a browser to see the result.

## Running both at once

```bash
uv run pytest --coverage-stats --coverage-stats-format html \
              --cov=src --cov-branch --cov-report=html:html-cov
```

## What's in the example

`src/asdf.py` contains a set of functions designed to exercise interesting coverage
edge cases:

| Function | What it demonstrates |
|---|---|
| `weird_corner_cases_1_while_loop_` | `while` loop that always runs (never exits normally) — partial branch |
| `weird_corner_cases_2_for_loop` | `for` loop over an empty iterable — partial branch |
| `weird_corner_cases_4_with_` | `with` statement — not marked partial by either tool |
| `weird_corner_cases_5_match` | `match` statement tested with only one case — `case 1:` shows as partial |
| `weird_case_multiple_statements_on_one_line` | multiple statements on one line |
| `not_covered` | function never called by any test |
