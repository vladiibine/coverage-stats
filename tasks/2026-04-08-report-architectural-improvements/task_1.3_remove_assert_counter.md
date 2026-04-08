# Task 1.3 — Remove `assert_counter.py`

**Priority:** P1
**Effort:** Low
**Impact:** Low (simplicity)
**Status: Done**

## Problem

`assert_counter.py` is an 18-line file that re-exports `record_assertion` and `distribute_asserts` from `ProfilerContext` in `profiler.py`. The actual logic was moved to `profiler.py` at some point, leaving this module as a dead indirection.

Its only reason to exist is that it occupies a layer in the import-linter contract:

```toml
layers = [
    "coverage_stats.plugin",
    "coverage_stats.reporters",
    "coverage_stats.assert_counter",   ← this layer exists only for this file
    "coverage_stats.profiler | coverage_stats.covers",
    "coverage_stats.store | coverage_stats.executable_lines",
]
```

Any code importing from `coverage_stats.assert_counter` is importing a thin wrapper around `profiler.py`, not the real thing. This creates confusion for anyone reading the import graph.

## Solution

1. Delete `src/coverage_stats/assert_counter.py`.
2. Update the import-linter contract in `pyproject.toml` to remove the `coverage_stats.assert_counter` layer entry.
3. Find all imports of `coverage_stats.assert_counter` (likely only in `tests/unit/test_assert_counter.py`) and redirect them to `coverage_stats.profiler`.
4. Rename or repurpose `test_assert_counter.py` to `test_profiler_assert_distribution.py` if the test file only covers the distribution logic.

**Check first:** Confirm no user-facing documentation references `assert_counter` as an extension point — if it's documented as part of the public API, deprecate instead of immediately deleting.
