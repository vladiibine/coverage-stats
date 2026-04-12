# coverage-stats-example

A self-contained example project that demonstrates the `coverage-stats` pytest plugin
alongside standard `coverage.py`, so you can compare their HTML outputs side by side.

## Setup

From this directory, install dependencies with `uv`:

## Projects with a `pyproject.toml`
```bash

# this will create a .venv and install this project's dependencies inside
uv sync --extra dev

# ...or activate any other venvs, and run `uv sync --extra dev --active` inside, to install the dependencies in those venvs
```

```bash
# ALTERNATIVELY, use your desired version of python
uv venv --python 3.10 .venv-3.10
```

This installs `pytest`, `coverage`, `pytest-cov`, `pytest-xdist`, and the
`coverage-stats` plugin (sourced from the parent repo via the workspace).

## Projects WITHOUT `pyptoject.toml`
```bash
# ...or use any python version
uv venv --python 3.10 .venv-3.10

.venv-3.10/bin/python -m ensurepip --upgrade

.venv-3.10/bin/python -m pip install -r requirements.txt
.venv-3.10/bin/python -m pip install pytest coverage pytest-cov pytest-xdist

.venv-3.10/bin/python -m pip install -e ../..

```

## Running coverage-stats

The `coverage-stats` plugin is activated with `--coverage-stats` and produces its own
HTML report in `coverage-stats-report/`:

### Running coverage-stats and coverage.py together WITHOUT `uv`
```bash
rm -rf coverage-stats-report html-cov; time ./.venv/bin/pytest tests --coverage-stats --coverage-stats-format html --coverage-stats-precision 6 -k test_load_ssl_config_verify_existing_file --cov --cov-report=html:html-cov --cov-branch; date
```

### Running covrage-stats and coverage.py together with `uv`
```bash
# use the default env
uv run pytest --coverage-stats --coverage-stats-precision 6 --coverage-stats-format html --cov=src --cov-branch --cov-report=html:html-cov

# or use another env
UV_PROJECT_ENVIRONMENT=.venv-311 uv run pytest --coverage-stats --coverage-stats-precision 6 --coverage-stats-format html --cov=src --cov-branch --cov-report=html:html-cov
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

## Running all three together: coverage-stats + coverage.py + xdist

All three tools can run simultaneously. The `pyproject.toml` already wires this up via
`addopts`, so a plain `pytest` invocation is enough:

```bash
uv run pytest
```

This runs with `-n auto` (xdist), `--cov=src` (coverage.py), and `--coverage-stats`
(coverage-stats) all active at the same time.

### How they coexist

**coverage-stats + coverage.py** share the same `sys.settrace` slot without conflict.
`coverage-stats` installs its `LineTracer` first, then forwards every trace event to
the previously registered tracer (coverage.py's), so both receive every event.

**coverage-stats + xdist** work out of the box. The plugin has built-in worker/controller
hooks: each xdist worker collects its own data, then ships it to the controller process
at the end of the session where it is merged before the report is written.

**coverage.py + xdist** requires two extra settings in `[tool.coverage.run]` (already
present in `pyproject.toml`):

```toml
parallel = true          # each worker writes its own .coverage.N file
concurrency = ["multiprocessing", "thread"]  # lets coverage.py trace worker subprocesses
```

`pytest-cov` merges the per-worker `.coverage.N` files automatically once all workers
finish.

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
