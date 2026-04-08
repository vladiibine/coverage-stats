# Task 4.1 — Coverage.py interop version guarding

**Priority:** P2
**Effort:** Low
**Impact:** Medium (robustness)

## Problem

`CoveragePyInterop` uses several coverage.py APIs that are not part of its documented public interface:

- `coverage.Coverage.current()` — undocumented class method
- `data.has_arcs()` — internal CoverageData method
- `data.add_lines(...)` — semi-public but format may change
- `data.add_arcs(...)` — same

There are no version checks or guards. A coverage.py major release (e.g., moving from 7.x to 8.x) could silently break the interop — the plugin would produce empty coverage.py reports without any warning.

The current `except Exception` in `inject_into_coverage_py` catches failures, but the warning message is generic and doesn't indicate whether the failure is a version incompatibility or a bug.

## Solution

**1. Add a minimum version check at import time** (in `coverage_py_interop.py` after task 1.2):

```python
_COVERAGE_MIN_VERSION = (7, 0)

def _check_coverage_version() -> bool:
    try:
        import coverage
        ver = tuple(int(x) for x in coverage.__version__.split(".")[:2])
        if ver < _COVERAGE_MIN_VERSION:
            warnings.warn(
                f"coverage-stats: coverage.py {coverage.__version__} is below the "
                f"minimum supported version {'.'.join(map(str, _COVERAGE_MIN_VERSION))}; "
                "interop disabled"
            )
            return False
        return True
    except ImportError:
        return False
```

**2. Guard each API call with a capability check:**

```python
def inject_into_coverage_py(self, store):
    try:
        import coverage as coverage_module
    except ImportError:
        return
    cov = coverage_module.Coverage.current()
    if cov is None:
        return
    if not hasattr(cov, 'get_data'):
        warnings.warn("coverage-stats: coverage.py API changed — interop skipped")
        return
    try:
        data = cov.get_data()
        if not hasattr(data, 'has_arcs') or not hasattr(data, 'add_lines'):
            warnings.warn("coverage-stats: coverage.py CoverageData API changed — interop skipped")
            return
        ...
    except Exception as exc:
        warnings.warn(f"coverage-stats: coverage.py interop failed (version mismatch?): {exc}")
```

**3. Add an integration test** that pins a specific coverage.py version and verifies the interop works. This can be a nox session that tests against coverage 6.x, 7.x, and the latest.
