# Task 5.2 — Move `covers_lines` to `ProfilerContext`

**Priority:** P0
**Effort:** Low
**Impact:** Medium (perf + clarity)

## Problem

The pattern `getattr(ctx.current_test_item, "_covers_lines", frozenset())` appears in three places:

1. `LineTracer._make_local_trace` inner closure (`profiler.py:291`)
2. `MonitoringLineTracer._monitoring_line` (`profiler.py:157`)
3. `ProfilerContext.distribute_asserts` (`profiler.py:56`)

This is fragile in two ways:
- If `resolve_covers` didn't run for some reason, the fallback `frozenset()` silently treats everything as incidental — no warning, no error.
- `getattr` with a string key is slower than a direct attribute access, and it's called on every single line event in the hot path.

The data flow is also implicit: `covers_lines` is set on `item` in `resolve_covers` (`covers.py`), then read back off `item` in the tracer via `getattr`. The `ProfilerContext` already owns all other per-test state (`current_test_item`, `current_phase`, `current_assert_count`, `current_test_lines`).

## Solution

Add `current_covers_lines` directly to `ProfilerContext`:

```python
@dataclass
class ProfilerContext:
    current_test_item: pytest.Item | None = None
    current_phase: str | None = None
    current_assert_count: int = 0
    source_dirs: list[str] = field(default_factory=list)
    current_test_lines: set[tuple[str, int]] = field(default_factory=set)
    pre_test_lines: set[tuple[str, int]] = field(default_factory=set)
    current_covers_lines: frozenset[tuple[str, int]] = frozenset()  # ← new
```

Set it in `pytest_runtest_setup` alongside `current_test_item`, immediately after calling `resolve_covers(item)`:

```python
def pytest_runtest_setup(self, item):
    resolve_covers(item)
    ctx.current_test_item = item
    ctx.current_covers_lines = getattr(item, "_covers_lines", frozenset())
    ctx.current_phase = "setup"
    ctx.current_test_lines.clear()
    ctx.current_assert_count = 0
```

Then replace all three `getattr(ctx.current_test_item, "_covers_lines", frozenset())` reads with `ctx.current_covers_lines`. In the tracer closures, `ctx` is already captured as a local variable, so this becomes a simple attribute access with no string lookup.

Reset to `frozenset()` in `pytest_runtest_teardown` (or rely on the next setup overwriting it).

**Also eliminates task 2.1's third optimization as a side effect**, since the `getattr` in the hot path is replaced by a direct field read.
