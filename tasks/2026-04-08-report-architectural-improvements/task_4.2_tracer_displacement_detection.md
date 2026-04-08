# Task 4.2 — Tracer displacement detection

**Priority:** P3
**Effort:** Low
**Impact:** Low (diagnostics)

## Problem

`LineTracer.start()` already detects whether it's still on top at reinstall time (via `current is self._installed_fn`), but there is no detection for the case where a third-party tracer displaces coverage-stats *during* a test's call phase.

If another plugin (e.g., a debugger, `pytest-timeout` with a signal-based tracer, or a custom plugin) installs a tracer mid-test, coverage-stats silently stops recording lines for that test. The test may pass, but its line data will be incomplete or empty — with no warning to the user.

## Solution

Add a displacement check at `pytest_runtest_teardown`, after the call phase completes but before assert distribution:

```python
def pytest_runtest_teardown(self, item, nextitem):
    if not self._enabled:
        return
    ctx = item.config._coverage_stats_ctx
    ctx.current_phase = "teardown"

    # Check if we were displaced during the call phase
    if self._tracer is not None and not self._tracer.is_active():
        warnings.warn(
            f"coverage-stats: tracer was displaced during test {item.nodeid!r}; "
            "line data for this test may be incomplete"
        )
        self._tracer.start()  # reinstall for teardown

    assert self._store is not None
    ctx.distribute_asserts(self._store)
    ctx.current_phase = None
    ctx.current_test_item = None
```

Add `is_active()` to both tracers:

```python
class LineTracer:
    def is_active(self) -> bool:
        return (
            self._installed_fn is not None
            and sys.gettrace() is self._installed_fn
        )

class MonitoringLineTracer:
    def is_active(self) -> bool:
        if self._tool_id is None:
            return False
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            return False
        # Check if our callback is still registered
        cb = monitoring.get_local_events(self._tool_id, ...)  # API varies
        return self._tool_id is not None  # simplified check
```

The exact `MonitoringLineTracer.is_active()` implementation depends on what `sys.monitoring` exposes for querying registration — fall back to tracking a `_stopped` flag if the API doesn't support querying.
