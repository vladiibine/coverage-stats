---
title: 'Project Scaffold'
type: 'chore'
created: '2026-03-15'
status: 'done'
baseline_commit: '529b202d3ea4194fb8172b4ddc4e5d2caa2ab82b'
context:
  - _bmad-output/planning-artifacts/architecture.md
---

# Project Scaffold

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The `coverage-stats` repository has no package structure, build config, or test layout — nothing can be imported, installed, or tested yet.

**Approach:** Create the full `pyproject.toml` + `src/coverage_stats/` skeleton with stub modules, `tests/` directory layout, and `.github/workflows/ci.yml`, so all subsequent feature stories have a working foundation to build on.

## Boundaries & Constraints

**Always:**
- `src/` layout with `setuptools` backend (PEP 517/518)
- Entry point: `[project.entry-points."pytest11"] coverage-stats = "coverage_stats.plugin"`
- Every module starts with `from __future__ import annotations`
- Zero third-party runtime deps — `setuptools` is build-time only
- `pathlib.Path` for any path references in code
- `__init__.py` exports only `covers` and `__version__`
- Dev deps: `pytest`, `ruff`, `mypy` only (no tox/nox — CI matrix handled by GitHub Actions)
- Install a python virtual env locally using `uv`

**Ask First:**
- If the `.gitignore` needs content beyond standard Python ignores (currently has 98 bytes — check before overwriting)

**Never:**
- Business logic in stubs — only `raise NotImplementedError` or `pass` and necessary imports/signatures
- Inline version string in `__init__.py` via `importlib.metadata` — define `__version__ = "0.1.0"` directly
- Any CDN links or external resources
- `tomllib` imports (config delegated to pytest)

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Editable install | `pip install -e ".[dev]"` in repo root | Exit 0; package importable | N/A |
| Package import | `python -c "from coverage_stats import covers, __version__"` | No error | N/A |
| Plugin discovery | `pytest --co -q` (no test files) | pytest output includes `coverage-stats` in plugin list (`pytest --trace-config`) | N/A |
| Test suite runs | `pytest tests/` with empty stubs | Collected 0 items, exit 0 | N/A |

</frozen-after-approval>

## Code Map

- `pyproject.toml` — package metadata, build backend, entry point, dev extras
- `src/coverage_stats/__init__.py` — public API: `covers`, `__version__`
- `src/coverage_stats/plugin.py` — `CoverageStatsPlugin` stub; hook signatures only
- `src/coverage_stats/profiler.py` — `ProfilerContext` stub; `LineTracer` stub
- `src/coverage_stats/covers.py` — `covers` decorator stub; `CoverageStatsResolutionError` stub
- `src/coverage_stats/store.py` — `LineData` dataclass stub; `SessionStore` stub
- `src/coverage_stats/assert_counter.py` — module stub
- `src/coverage_stats/reporters/__init__.py` — empty
- `src/coverage_stats/reporters/html.py` — `write_html` stub
- `src/coverage_stats/reporters/json_reporter.py` — `write_json` stub
- `src/coverage_stats/reporters/csv_reporter.py` — `write_csv` stub
- `tests/conftest.py` — empty (placeholder for shared fixtures)
- `tests/unit/test_covers.py` — empty placeholder
- `tests/unit/test_profiler.py` — empty placeholder
- `tests/unit/test_store.py` — empty placeholder
- `tests/unit/test_reporters/test_html.py` — empty placeholder
- `tests/unit/test_reporters/test_json.py` — empty placeholder
- `tests/unit/test_reporters/test_csv.py` — empty placeholder
- `tests/integration/test_plugin_basic.py` — empty placeholder
- `.github/workflows/ci.yml` — matrix: python 3.9–3.13 × pytest 7/8
- `README.md` — minimal: project name, install, usage

## Tasks & Acceptance

**Execution:**
- [ ] `pyproject.toml` -- CREATE -- defines build backend (setuptools ≥61), project metadata (name=coverage-stats, version=0.1.0, requires-python=≥3.9, dependencies=[pytest]), dev extras (pytest, ruff, mypy), and pytest11 entry point
- [ ] `src/coverage_stats/__init__.py` -- CREATE -- `__version__ = "0.1.0"` and `from coverage_stats.covers import covers`
- [ ] `src/coverage_stats/plugin.py` -- CREATE -- `CoverageStatsPlugin` class with `_enabled: bool`; stub hook methods: `pytest_addoption`, `pytest_configure`, `pytest_collection_finish`, `pytest_runtest_setup`, `pytest_runtest_call`, `pytest_runtest_teardown`, `pytest_assertion_pass`, `pytest_sessionfinish`; each body is `if not self._enabled: return` followed by `raise NotImplementedError`
- [ ] `src/coverage_stats/profiler.py` -- CREATE -- `ProfilerContext` dataclass with fields `current_test_item`, `current_phase`, `current_assert_count`, `source_dirs`; `LineTracer` class stub with `start()` / `stop()` / `_trace()` methods
- [ ] `src/coverage_stats/covers.py` -- CREATE -- `CoverageStatsError(Exception)`, `CoverageStatsResolutionError(CoverageStatsError)`, `covers` decorator that stores raw refs as `_covers_refs` on the wrapped function and returns it unchanged
- [ ] `src/coverage_stats/store.py` -- CREATE -- `LineData` dataclass (four `int` fields); `SessionStore` class with `get_or_create`, `merge`, `to_dict`, `from_dict` stubs
- [ ] `src/coverage_stats/assert_counter.py` -- CREATE -- module-level docstring + `from __future__ import annotations`; function stub `handle_assertion_pass(context: ProfilerContext) -> None`
- [ ] `src/coverage_stats/reporters/__init__.py` -- CREATE -- empty (package marker)
- [ ] `src/coverage_stats/reporters/html.py` -- CREATE -- `write_html(store, output_dir: Path) -> None` stub
- [ ] `src/coverage_stats/reporters/json_reporter.py` -- CREATE -- `write_json(store, output_dir: Path) -> None` stub
- [ ] `src/coverage_stats/reporters/csv_reporter.py` -- CREATE -- `write_csv(store, output_dir: Path) -> None` stub
- [ ] `tests/conftest.py` -- CREATE -- `from __future__ import annotations` only (placeholder)
- [ ] `tests/unit/`, `tests/unit/test_reporters/`, `tests/integration/` -- CREATE placeholder files (`test_covers.py`, `test_profiler.py`, `test_store.py`, `test_html.py`, `test_json.py`, `test_csv.py`, `test_plugin_basic.py`) -- each file has only `from __future__ import annotations` (valid empty test modules)
- [ ] `.github/workflows/ci.yml` -- CREATE -- matrix `python-version: [3.9, 3.10, 3.11, 3.12, 3.13]` × `pytest-version: [">=7,<8", ">=8,<9"]`; steps: checkout → setup-python → `pip install -e ".[dev]" "pytest{pytest-version}"` → `ruff check src/` → `pytest tests/`
- [ ] `README.md` -- CREATE -- project name, one-line description, install snippet, basic usage (if already exists, check content first)
- [ ] `.gitignore` -- VERIFY/EXTEND -- check existing content; add Python standard ignores if missing (`__pycache__`, `*.egg-info`, `dist/`, `.mypy_cache/`, `.ruff_cache/`)

**Acceptance Criteria:**
- Given the repo root, when `pip install -e ".[dev]"` runs, then it exits 0 and `coverage_stats` is importable
- Given an installed package, when `python -c "from coverage_stats import covers, __version__; print(__version__)"`, then it prints `0.1.0`
- Given the installed plugin, when `pytest --trace-config -q` runs, then output contains `coverage-stats`
- Given the test directory, when `pytest tests/ -q`, then it exits 0 with no errors (0 tests collected is acceptable)
- Given `src/`, when `ruff check src/` runs, then it exits 0

## Design Notes

**`covers` decorator stub:** Must store refs without resolving them — resolution happens at `pytest_runtest_setup`. The decorator returns the original function with `_covers_refs` attribute set.

```python
def covers(*refs):
    def decorator(fn):
        fn._covers_refs = refs
        return fn
    return decorator
```

**`ProfilerContext` fields must match exactly:**
```python
@dataclass
class ProfilerContext:
    current_test_item: Any | None = None
    current_phase: str | None = None  # "setup" | "call" | "teardown"
    current_assert_count: int = 0
    source_dirs: list[str] = field(default_factory=list)
```

## Verification

**Commands:**
- `pip install -e ".[dev]"` -- expected: exit 0, no errors
- `python -c "from coverage_stats import covers, __version__; print(__version__)"` -- expected: prints `0.1.0`
- `pytest --trace-config -q 2>&1 | grep coverage-stats` -- expected: line containing `coverage-stats`
- `pytest tests/ -q` -- expected: exit 0
- `ruff check src/` -- expected: exit 0
