# Plan: coverage.py Interoperability

## Goal

Make coverage-stats and coverage.py work together correctly on all Python versions, with coverage-stats able to feed its collected data (lines + branch arcs) back to coverage.py so that coverage.py's own reports are accurate even when coverage-stats has displaced its tracer.

---

## Decision tree (from design discussion)

```
if py < 3.12:
    if coverage-stats active (--coverage-stats):
        if coverage.py active:
            # Replace coverage.py's tracer entirely.
            # Feed line + arc data back to coverage.py at session end.
            # Requires AST arc construction (from_line, to_line pairs).
        else:
            # Normal chaining approach: install on top of whatever
            # sys.gettrace() returns
    else:
        # coverage-stats not active: complete no-op.
        # Do not touch sys.settrace. Other tools unaffected.
else:  # py >= 3.12
    # Use sys.monitoring. No sys.settrace conflicts.
```

---

## Step 1: Two-phase tracer install (recover pre-test lines)

**Problem:** The current code starts the tracer in `pytest_collection_finish`, missing `def`/`class`/module-level lines executed during collection.

**Solution:** Install in two phases:
1. `pytest_sessionstart` (`trylast=True`) — start the tracer so collection-time lines are captured into `pre_test_lines`.
2. `pytest_collection_finish` (`trylast=True`) — call `tracer.start()` again to reinstall ourselves on top after coverage.py's stop/restart cycle around collection has completed. This updates `_prev_trace` to whatever coverage.py reinstalled.

`start()` is already safe to call twice — it snapshots `sys.gettrace()` each time and reinstalls cleanly.

**Applies to:** all `py < 3.12` active branches (both 1.1.1.1 and 1.1.1.2).

---

## Step 2: Detect whether coverage.py is active

At `pytest_configure` time, check:

```python
def _is_coverage_py_active(config: pytest.Config) -> bool:
    return config.pluginmanager.hasplugin("pytest_cov")
```

This is available at `pytest_configure` time and is reliable. Store the result on the plugin instance so later hooks can branch on it.

---

## Step 3: AST arc construction for coverage.py (py < 3.12, both tools active)

The existing `_analyze_branches` method infers which branches were taken (true/false) from execution counts, and knows the `to_line` for true branches and for false branches that have an explicit `else`/`elif`. The missing piece is the `to_line` for **false branches without `else`** (i.e., when the condition was false and execution fell through to the next statement after the block).

**New function:** `_compute_arcs(path, lines) -> dict[str, list[tuple[int, int]]]`

For each `ast.If`, `ast.While`, `ast.For` node:
- True arc `(header_line, body[0].lineno)` — include if `body_count > 0`.
- False arc with `orelse`: `(header_line, orelse[0].lineno)` — include if `_count(orelse[0].lineno) > 0`.
- False arc without `orelse`: `(header_line, next_sibling_lineno)` — include if `if_count > body_count`.

**Finding `next_sibling_lineno`:** Walk the AST keeping a parent map. For each branching node, find its position in the parent body list, then take `parent.body[i+1].lineno`. If the node is last in its parent body, recurse up to the grandparent. This handles nested structures correctly.

For `ast.Match` cases, construct arcs similarly using the case pattern line and body first line.

This function returns the set of arcs that were actually traversed, suitable for passing to `coverage.CoverageData.add_arcs()`.

---

## Step 4: Feed data to coverage.py at session end

In `pytest_sessionfinish`, before coverage.py writes its report:

```python
# Hook with tryfirst=True so we run before pytest-cov's sessionfinish
@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(self, session, exitstatus):
    if self._coverage_py_active:
        import coverage as coverage_module
        cov = coverage_module.Coverage.current()
        if cov is not None:
            data = cov.get_data()
            # Line data
            lines_by_file = self._store.lines_by_file()  # new helper
            data.add_lines(lines_by_file)
            # Arc data
            arcs_by_file = _compute_arcs_for_all_files(self._store, ...)
            data.add_arcs(arcs_by_file)
```

**Why `tryfirst=True` works for both scenarios:**
- **Scenario 1 (live report):** pytest-cov generates its report in its own `pytest_sessionfinish`. By running first, we inject data before coverage.py calls `cov.save()` and generates the report.
- **Scenario 2 (`coverage report` later):** Coverage.py persists data to `.coverage` in `cov.save()`. Since we injected before that, the data is in the file when `coverage report` runs afterwards.

**New helper on `SessionStore`:** `lines_by_file() -> dict[str, list[int]]` — groups store keys by filename, returns `{abs_path: [lineno, ...]}` format that `CoverageData.add_lines()` expects.

---

## Step 5: Python 3.12+ path — sys.monitoring

On Python >= 3.12, skip `sys.settrace` entirely and register via `sys.monitoring`:

```python
TOOL_ID = sys.monitoring.COVERAGE_ID  # or a custom tool ID (4 or 5), if COVERAGE_ID was already claimed

sys.monitoring.use_tool_id(TOOL_ID, "coverage-stats")
sys.monitoring.set_events(TOOL_ID, sys.monitoring.events.LINE)
sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.LINE, self._monitoring_callback)
```

The callback receives `(code, line_number)` and maps to the same store logic as the current `line` event handler.

Branch analysis at report time stays the same (AST + count heuristics) — no need to feed arcs to coverage.py because on 3.12+ both tools register independently via `sys.monitoring` and both receive all events without conflict.

**Note:** `sys.monitoring` does not have the "replace vs. chain" problem. Multiple tools can register independently for the same events. Coverage.py on 3.12+ uses `sys.monitoring.COVERAGE_ID`; coverage-stats should use a different tool ID to avoid colliding.

---

## Step 6: no-op path (coverage-stats not active)

No changes needed. The existing `if not self._enabled: return` guards in every hook already make the plugin fully transparent. Explicitly: do not call `sys.settrace`, do not call `sys.monitoring.use_tool_id`, do nothing.

---

## Files to change

| File | Changes |
|---|---|
| `src/coverage_stats/plugin.py` | Add `_is_coverage_py_active` detection; split `pytest_sessionstart` / `pytest_collection_finish` into two-phase install; add `tryfirst=True` to `pytest_sessionfinish`; add data injection logic |
| `src/coverage_stats/profiler.py` | Add Python 3.12+ `sys.monitoring` implementation as an alternative to `LineTracer`; keep `LineTracer` for < 3.12 |
| `src/coverage_stats/reporters/report_data.py` | Add `_compute_arcs()` function that produces `(from_line, to_line)` pairs with next-sibling AST traversal for no-else false branches |
| `src/coverage_stats/store.py` | Add `lines_by_file() -> dict[str, list[int]]` helper |

---

## What this does NOT change

- The `_analyze_branches` heuristic used for coverage-stats' own branch reporting is unchanged.
- The `pre_test_lines` / `_flush_pre_test_lines` mechanism is unchanged.
- xdist support is unchanged; data injection into coverage.py happens on the controller after merge, same as today.
- The `@covers` / deliberate vs. incidental distinction is unchanged.
