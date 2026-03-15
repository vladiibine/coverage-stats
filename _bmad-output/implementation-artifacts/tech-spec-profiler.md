---
title: 'sys.settrace Profiler'
type: 'feature'
created: '2026-03-15'
status: 'done'
baseline_commit: '4caa821f193077fbee6697e6944800bdabe02a7e'
context:
  - _bmad-output/planning-artifacts/architecture.md
---

# sys.settrace Profiler

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `LineTracer` is a stub — no execution counts are accumulated, so the store is always empty and deliberate/incidental split never happens.

**Approach:** Fully implement `LineTracer` in `profiler.py` (init, start, stop, _trace hot path) and wire all phase-tracking hooks in `plugin.py` (configure, setup, call, teardown, sessionfinish). After this story, `pytest --coverage-stats` on a test suite populates `SessionStore` with per-line execution counts correctly split into deliberate vs incidental buckets.

## Boundaries & Constraints

**Always:**
- `from __future__ import annotations` in every module
- `ProfilerContext` stored on `config._coverage_stats_ctx`; `SessionStore` and `LineTracer` stored as `self._store` and `self._tracer` on `CoverageStatsPlugin`
- Trace function chained: `sys.gettrace()` saved at `start()`; restored at `stop()`; called on every event before our own logic
- Line accumulation: **only during `call` phase** (`context.current_phase == "call"`)
- Source scoping: a line is accumulated only if `str(Path(frame.f_code.co_filename).resolve())` starts with one of the configured `source_dirs` absolute prefixes; if `source_dirs` is empty, skip files under `sys.prefix` and containing `site-packages`
- Deliberate: `(abs_path, lineno) in context.current_test_item._covers_lines` — else incidental
- Errors inside `_trace`: caught by broad `except Exception`, emitted as `warnings.warn(f"coverage-stats: tracer error: {exc}")` — never raise
- `_trace` must return itself on `call` events (to receive line events in every scope); return value on other events is ignored by Python
- `pathlib.Path` for all path operations; stdlib + pytest only

**Ask First:**
- If `source_dirs` parsing from pytest config options is ambiguous

**Never:**
- Accumulate during `setup` or `teardown` phases
- `raise` inside `_trace` for any reason
- `os.path` — use `pathlib.Path`
- Implement assert distribution here (that belongs to the assert-counter story)
- Implement reporters here (still stubs)

## I/O & Edge-Case Matrix

| Scenario | State | Expected Behaviour |
|----------|-------|-------------------|
| Line in source dir, call phase, deliberate | `current_phase="call"`, path in source_dirs, lineno in `_covers_lines` | `store.get_or_create((path, lineno)).deliberate_executions += 1` |
| Line in source dir, call phase, incidental | same but lineno not in `_covers_lines` | `.incidental_executions += 1` |
| Line outside source dir | path not startswith any source_dir | no accumulation |
| Line during setup/teardown | `current_phase != "call"` | no accumulation |
| No active test item | `current_test_item is None` | no accumulation (skip safely) |
| Exception in `_trace` | any exception raised internally | caught, `warnings.warn`, tracing continues |
| Pre-existing trace function (debugger) | `sys.gettrace()` non-None at start | chained: called first on every event |
| `source_dirs` empty | no `coverage_stats_source` config | warn once, skip stdlib/site-packages paths |

</frozen-after-approval>

## Code Map

- `src/coverage_stats/profiler.py` — `LineTracer`: add `__init__`, implement `start`, `stop`, `_trace`; `ProfilerContext` unchanged
- `src/coverage_stats/plugin.py` — `pytest_configure`: create context/store/tracer, start tracer; `pytest_runtest_setup/call/teardown`: set phase; `pytest_sessionfinish`: stop tracer
- `tests/unit/test_profiler.py` — unit tests for `LineTracer` mechanics

## Tasks & Acceptance

**Execution:**
- [ ] `src/coverage_stats/profiler.py` -- IMPLEMENT `LineTracer` -- add `__init__(self, context, store)`; implement `start()` (save+set trace), `stop()` (restore), `_trace()` (chain, accumulate on line events, return self on call events, catch+warn exceptions)
- [ ] `src/coverage_stats/plugin.py` -- IMPLEMENT hooks --
  - `pytest_configure`: create `ProfilerContext`, parse `source_dirs` from `config.getini("coverage_stats_source")`, create `SessionStore`, create `LineTracer(ctx, store)`, start tracer, store `config._coverage_stats_ctx = ctx`; store `self._store = store`, `self._tracer = tracer`
  - `pytest_addoption`: add `addini("coverage_stats_source", ...)` alongside existing options
  - `pytest_runtest_setup`: after `resolve_covers(item)`, set `ctx.current_test_item = item` and `ctx.current_phase = "setup"`
  - `pytest_runtest_call`: set `ctx.current_phase = "call"`
  - `pytest_runtest_teardown`: set `ctx.current_phase = "teardown"` at entry; at exit reset `ctx.current_phase = None` and `ctx.current_test_item = None`
  - `pytest_sessionfinish`: call `self._tracer.stop()`; leave reporters as `pass` (not `raise NotImplementedError`) — reporters come in a later story
  - `pytest_collection_finish`: change to `pass` (no-op until later story)
  - `pytest_assertion_pass`: keep `raise NotImplementedError` — wired in the assert-counter story
- [ ] `tests/unit/test_profiler.py` -- IMPLEMENT -- tests: `start` saves and sets trace; `stop` restores previous trace; `_trace` accumulates deliberate on call phase; `_trace` accumulates incidental on call phase; `_trace` skips during setup/teardown; `_trace` skips files outside source_dirs; `_trace` skips when no test item; `_trace` catches exceptions and warns; `_trace` chains previous trace function; `_trace` returns self on call event

**Acceptance Criteria:**
- Given a source file in `source_dirs` and a test with `@covers(my_fn)`, when the test's call phase executes lines in `my_fn`, then `store.get_or_create((abs_path, lineno)).deliberate_executions > 0`
- Given the same file executed by a test WITHOUT `@covers`, then `.incidental_executions > 0` for those lines
- Given a file not under any `source_dir`, when lines execute, then no entry is created in the store
- Given an exception raised inside `_trace`, when a line event fires, then `warnings.warn` is called and the tracer continues (does not crash the test run)
- Given `pytest tests/unit/test_profiler.py -v`, then all tests pass
- Given `ruff check src/coverage_stats/profiler.py src/coverage_stats/plugin.py`, then exit 0

## Design Notes

**`_trace` hot-path skeleton:**
```python
def _trace(self, frame, event, arg):
    try:
        if self._prev_trace is not None:
            self._prev_trace(frame, event, arg)
        if event == "call":
            return self._trace
        if event != "line":
            return None
        ctx = self._context
        if ctx.current_phase != "call" or ctx.current_test_item is None:
            return None
        filename = str(Path(frame.f_code.co_filename).resolve())
        if not self._in_scope(filename):
            return None
        lineno = frame.f_lineno
        key = (filename, lineno)
        ld = self._store.get_or_create(key)
        if key in ctx.current_test_item._covers_lines:
            ld.deliberate_executions += 1
        else:
            ld.incidental_executions += 1
    except Exception as exc:
        warnings.warn(f"coverage-stats: tracer error: {exc}")
    return None
```

**`_in_scope` helper** (on `LineTracer`): if `source_dirs` non-empty, return `any(filename.startswith(d) for d in self._context.source_dirs)`; else return `"site-packages" not in filename and not filename.startswith(sys.prefix)`.

## Verification

**Commands:**
- `.venv/bin/pytest tests/unit/test_profiler.py -v` -- expected: all tests pass
- `.venv/bin/pytest tests/ -v --ignore=tests/integration` -- expected: all unit tests pass
- `.venv/bin/ruff check src/coverage_stats/profiler.py src/coverage_stats/plugin.py` -- expected: exit 0
