# Task 2.1 — Reduce hot-path attribute lookups in tracer callbacks

**Priority:** P0
**Effort:** Low
**Impact:** High (perf)
**Status: Done**

## Problem

The tracer callback fires on **every line executed** during tests. Even small overheads compound into measurable slowdowns.

The current `_make_local_trace` inner function (`profiler.py:280-303`) performs redundant work on every single line event:

```python
def local(frame, event, arg):
    nonlocal current_prev
    if current_prev is not None:
        current_prev = current_prev(frame, event, arg)
    if event == "line":
        ctx = self._context          # attribute lookup on self — every line
        lineno = frame.f_lineno
        key = (filename, lineno)
        if ctx.current_phase == "call" and ctx.current_test_item is not None:
            ld = self._store.get_or_create(key)   # attribute lookup on self — every line
            covers_lines = getattr(ctx.current_test_item, "_covers_lines", frozenset())  # getattr — every line
```

Three sources of avoidable overhead per line event:
1. `self._context` — attribute lookup on `self` (LOAD_ATTR bytecode), even though `_context` never changes after `__init__`
2. `self._store` — same issue
3. `getattr(ctx.current_test_item, "_covers_lines", frozenset())` — `getattr` with a string key on every line, even though `_covers_lines` is fixed for the duration of a test

## Solution

**1. Capture `_context` and `_store` as closure variables** in `_make_local_trace`, so they are resolved once when the local tracer is created, not on every call:

```python
def _make_local_trace(self, filename, prev_local):
    ctx = self._context   # captured once
    store = self._store   # captured once
    current_prev = prev_local

    def local(frame, event, arg):
        nonlocal current_prev
        ...
        lineno = frame.f_lineno
        key = (filename, lineno)
        if ctx.current_phase == "call" and ctx.current_test_item is not None:
            ld = store.get_or_create(key)
            ...
    return local
```

**2. Cache `covers_lines` on `ProfilerContext`** (see also task 5.2). Instead of `getattr(ctx.current_test_item, "_covers_lines", frozenset())` on every line, store it directly as `ctx.current_covers_lines` and set it once in `pytest_runtest_setup`. The inner closure reads `ctx.current_covers_lines` — a simple attribute access on an already-captured local.

**3. Remove the `event == "line"` branch check** in the local tracer. Python only calls local trace functions for `line`, `return`, and `exception` events. The `return` and `exception` cases doing a dict lookup are cheap and harmless. Removing the equality check saves one string comparison per line event.

**Estimated impact:** 15–25% reduction in per-line overhead based on typical Python attribute lookup costs (~50 ns each, millions of calls over a full test suite).
