---
title: 'Assert Counter'
type: 'feature'
created: '2026-03-15'
status: 'done'
baseline_commit: '7879f8a82fcf41767a6efc36ea4ffcfedf01a247'
context:
  - _bmad-output/planning-artifacts/architecture.md
---

# Assert Counter

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `pytest_assertion_pass` events are unhandled (no-op stub) and `pytest_runtest_teardown` never distributes assert counts to executed lines — so `incidental_asserts` and `deliberate_asserts` stay zero forever.

**Approach:** Add `current_test_lines: set[tuple[str, int]]` to `ProfilerContext` and populate it in `LineTracer._trace`; implement `record_assertion` and `distribute_asserts` in `assert_counter.py`; wire both into the existing plugin hooks.

## Boundaries & Constraints

**Always:**
- `from __future__ import annotations` in every module
- `record_assertion(ctx)` increments `ctx.current_assert_count` only when `ctx.current_phase == "call"` and `ctx.current_test_item is not None`
- `distribute_asserts(ctx, store)` distributes the full `ctx.current_assert_count` to every key in `ctx.current_test_lines` — each line gets `+count`, not `count / n`
- Deliberate/incidental split in `distribute_asserts` uses `getattr(ctx.current_test_item, "_covers_lines", frozenset())` — same pattern as `LineTracer._trace`
- `distribute_asserts` resets `ctx.current_assert_count = 0` and clears `ctx.current_test_lines` before returning
- `LineTracer._trace` adds `key` to `ctx.current_test_lines` immediately after adding to `incidental_executions` or `deliberate_executions`
- `pytest_runtest_setup` in `plugin.py` defensively clears `ctx.current_test_lines` and `ctx.current_assert_count = 0` before each test
- `pytest_runtest_teardown` calls `distribute_asserts(ctx, self._store)` before resetting `current_phase` and `current_test_item`
- `current_test_lines` field type: `set[tuple[str, int]]` with `field(default_factory=set)`
- stdlib + pytest only

**Ask First:**
- If any other module needs to read or write `current_test_lines` beyond `profiler.py` and `assert_counter.py`

**Never:**
- Average or divide `current_assert_count` across lines — each line gets the full count
- Distribute during setup or teardown phase — only accumulate during "call" phase
- Modify `store.py` or `covers.py`
- Add a new pytest hook other than those already present in `plugin.py`

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| No asserts | `current_assert_count = 0` at teardown | store unchanged; lines untouched | — |
| 2 asserts, 3 incidental lines | count=2, lines={(f,1),(f,2),(f,3)}, `_covers_lines=frozenset()` | each line: `incidental_asserts += 2` | — |
| Mixed deliberate/incidental | count=1, `_covers_lines={(f,1)}`, executed={(f,1),(f,2)} | (f,1) `deliberate_asserts+=1`; (f,2) `incidental_asserts+=1` | — |
| Assertion fires during setup phase | `current_phase = "setup"` when hook fires | count NOT incremented | — |
| Empty executed lines, non-zero count | count=3, `current_test_lines={}` | store unchanged; count reset to 0 | — |
| New test resets state | previous test left count=5, lines={(f,1)} | setup clears both before next test begins | — |

</frozen-after-approval>

## Code Map

- `src/coverage_stats/profiler.py` — add `current_test_lines` field to `ProfilerContext`; update `_trace` to populate it
- `src/coverage_stats/assert_counter.py` — implement `record_assertion` and `distribute_asserts`
- `src/coverage_stats/plugin.py` — wire `record_assertion` into `pytest_assertion_pass`; call `distribute_asserts` in `pytest_runtest_teardown`; defensive reset in `pytest_runtest_setup`
- `tests/unit/test_assert_counter.py` — unit tests for all I/O matrix scenarios

## Tasks & Acceptance

**Execution:**
- [ ] `src/coverage_stats/profiler.py` -- UPDATE -- add `current_test_lines: set[tuple[str, int]] = field(default_factory=set)` to `ProfilerContext`; in `_trace`, after the `ld.deliberate_executions += 1` / `ld.incidental_executions += 1` lines, add `ctx.current_test_lines.add(key)`
- [ ] `src/coverage_stats/assert_counter.py` -- IMPLEMENT -- replace stub with: `record_assertion(ctx: ProfilerContext) -> None` (guard: phase must be "call" and item not None); `distribute_asserts(ctx: ProfilerContext, store: Any) -> None` (iterate `ctx.current_test_lines`, split deliberate/incidental via `_covers_lines`, add count to each `LineData`, reset count and clear lines)
- [ ] `src/coverage_stats/plugin.py` -- UPDATE -- `pytest_assertion_pass`: replace no-op body with `from coverage_stats.assert_counter import record_assertion; record_assertion(ctx)`; `pytest_runtest_setup`: add `ctx.current_test_lines.clear(); ctx.current_assert_count = 0` after `ctx.current_phase = "setup"`; `pytest_runtest_teardown`: add `from coverage_stats.assert_counter import distribute_asserts; distribute_asserts(ctx, self._store)` before the existing resets; remove now-redundant `ctx.current_assert_count = 0`
- [ ] `tests/unit/test_assert_counter.py` -- IMPLEMENT -- tests for: zero asserts no-op, 2 asserts 3 incidental lines, mixed deliberate/incidental, assertion during setup phase ignored, empty lines with non-zero count

**Acceptance Criteria:**
- Given `current_assert_count = 0` at teardown, when `distribute_asserts` is called, then no `LineData` fields are modified
- Given 2 passing assertions and 3 lines executed (all incidental), when `distribute_asserts` runs, then each line's `incidental_asserts == 2` and `deliberate_asserts == 0`
- Given 1 passing assertion and 2 lines executed (`(f,1)` deliberate, `(f,2)` incidental), when `distribute_asserts` runs, then `(f,1).deliberate_asserts == 1` and `(f,2).incidental_asserts == 1`
- Given `current_phase = "setup"` when `pytest_assertion_pass` fires, when `record_assertion` is called, then `current_assert_count` is unchanged
- Given `pytest tests/unit/test_assert_counter.py -v`, then all tests pass

## Design Notes

**`distribute_asserts` skeleton:**
```python
def distribute_asserts(ctx: ProfilerContext, store: Any) -> None:
    count = ctx.current_assert_count
    if count and ctx.current_test_lines:
        covers_lines = getattr(ctx.current_test_item, "_covers_lines", frozenset())
        for key in ctx.current_test_lines:
            ld = store.get_or_create(key)
            if key in covers_lines:
                ld.deliberate_asserts += count
            else:
                ld.incidental_asserts += count
    ctx.current_assert_count = 0
    ctx.current_test_lines.clear()
```

**Why full count per line, not divided:** Assert density is a per-line metric measuring "how assertion-rich were the tests that exercised this line". Dividing would dilute signal as functions grow. Each executed line inherits the full assertion weight of its test.

## Verification

**Commands:**
- `.venv/bin/pytest tests/unit/test_assert_counter.py tests/unit/test_profiler.py -v` -- expected: all tests pass
- `.venv/bin/ruff check src/coverage_stats/assert_counter.py src/coverage_stats/profiler.py src/coverage_stats/plugin.py` -- expected: exit 0
