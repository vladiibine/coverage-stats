# Task 4.3 — `MonitoringLineTracer` tool ID fallback warnings

**Priority:** P3
**Effort:** Low
**Impact:** Low (correctness)

## Problem

`MonitoringLineTracer.start()` tries tool IDs in order `(4, 5, 3, 2)`:

```python
for tool_id in (4, 5, 3, 2):
    try:
        monitoring.use_tool_id(tool_id, "coverage-stats")
        self._tool_id = tool_id
        break
    except ValueError:
        continue
```

According to CPython internals, tool IDs 0–3 are reserved for standard tools:
- 0: Debugger
- 1: Coverage (used by coverage.py)
- 2: Profiler
- 3: Optimizer

Claiming IDs 2 or 3 may conflict with future CPython features, with coverage.py if it moves to a different ID, or with third-party tools that legitimately use those IDs. The current code silently takes a reserved ID with no indication to the user.

Additionally, if all IDs are exhausted, the plugin silently disables tracing with only a `warnings.warn` — easy to miss in a large test run output.

## Solution

Separate the reserved-ID fallback into an explicit, louder warning:

```python
def start(self) -> None:
    if self._tool_id is not None:
        return

    monitoring = getattr(sys, "monitoring", None)
    if monitoring is None:
        warnings.warn("coverage-stats: sys.monitoring not available (requires Python 3.12+)")
        return

    # Try non-reserved IDs first (4 and 5 are user-space)
    for tool_id in (4, 5):
        try:
            monitoring.use_tool_id(tool_id, "coverage-stats")
            self._tool_id = tool_id
            break
        except ValueError:
            continue

    # Fall back to reserved IDs with an explicit warning
    if self._tool_id is None:
        warnings.warn(
            "coverage-stats: tool IDs 4 and 5 are unavailable; "
            "falling back to reserved IDs (2 or 3) which may conflict "
            "with other monitoring tools"
        )
        for tool_id in (3, 2):
            try:
                monitoring.use_tool_id(tool_id, "coverage-stats")
                self._tool_id = tool_id
                break
            except ValueError:
                continue

    if self._tool_id is None:
        warnings.warn(
            "coverage-stats: no sys.monitoring tool ID available; "
            "line tracing is DISABLED for this session. "
            "Check for other tools using sys.monitoring."
        )
        return

    monitoring.set_events(self._tool_id, monitoring.events.LINE)
    monitoring.register_callback(self._tool_id, monitoring.events.LINE, self._monitoring_line)
```

The final "tracing DISABLED" warning should be more prominent (consider `warnings.warn(..., stacklevel=2)` or writing directly to `sys.stderr`) since it means the plugin produces no data.
