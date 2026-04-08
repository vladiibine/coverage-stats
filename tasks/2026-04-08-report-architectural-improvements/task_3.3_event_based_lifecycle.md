# Task 3.3 — Event-based architecture for test lifecycle

**Priority:** P4
**Effort:** High
**Impact:** Low (premature unless needed)

## Problem

The plugin directly calls `resolve_covers`, `ctx.distribute_asserts`, and `_flush_pre_test_lines` from specific hook methods. Adding a new per-test behavior (e.g., recording test duration per line, per-line assertion granularity, or custom line classification) currently requires:

1. Modifying `CoverageStatsPlugin` (or one of its coordinators after task 1.1)
2. Adding a new field to `ProfilerContext`
3. Adding a new method to `SessionStore`

There is no subscription mechanism — every new behavior must be wired in at the call site.

## Solution

**Note: This task is speculative and should only be pursued if multiple independent extension points are needed. The current `CoverageStatsCustomization` entry point is sufficient for most use cases.**

Introduce a lightweight lifecycle event system that observers can subscribe to:

```python
from enum import Enum
from typing import Callable

class LifecycleEvent(str, Enum):
    TEST_SETUP = "test_setup"
    TEST_CALL_START = "test_call_start"
    TEST_TEARDOWN = "test_teardown"
    LINE_RECORDED = "line_recorded"
    SESSION_FINISH = "session_finish"

class LifecycleBus:
    def __init__(self) -> None:
        self._handlers: dict[LifecycleEvent, list[Callable]] = defaultdict(list)

    def subscribe(self, event: LifecycleEvent, handler: Callable) -> None:
        self._handlers[event].append(handler)

    def emit(self, event: LifecycleEvent, **kwargs) -> None:
        for handler in self._handlers[event]:
            handler(**kwargs)
```

Plugin hooks emit events:

```python
def pytest_runtest_setup(self, item):
    resolve_covers(item)
    self._bus.emit(LifecycleEvent.TEST_SETUP, item=item, ctx=ctx, store=self._store)

def pytest_runtest_teardown(self, item, nextitem):
    ctx.distribute_asserts(self._store)
    self._bus.emit(LifecycleEvent.TEST_TEARDOWN, item=item, ctx=ctx, store=self._store)
```

Custom behaviors subscribe via `CoverageStatsCustomization.configure_bus(bus)`.

**Why P4:** The event model adds indirection and makes the data flow harder to follow. It solves a problem that doesn't exist yet — there are currently no third-party extensions that need this. Revisit if/when multiple independent extension points emerge in practice.
