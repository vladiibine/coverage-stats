# Plan: Fix coverage.py interop on Python < 3.12

Vlad: The plan in this document has been implemented, and as far of this writing, it works. This supersedes documents 2026-04-05-make-coverage-py-interop.md and  2026-04-05-make-coverage-py-interop-plan.md, where the main problem was not 

## Root Cause

The injection code in `_save_with_injection()` (plugin.py:313) calls:

```python
data.add_lines(plugin._store.lines_by_file())   # step 1
data.add_arcs(...)                                # step 2
```

When coverage.py is configured with `--cov-branch`, its `CoverageData` object is in **arc mode** (`has_arcs = True`). In arc mode, `add_lines()` raises:

```
DataError: Can't add line measurements to existing branch data
```

This is enforced in `coverage/sqldata.py:585-592` — coverage.py considers line data and arc data mutually exclusive. Since the exception is caught by the broad `except Exception` block (plugin.py:318), `add_arcs()` never runs either. Coverage.py ends up with zero data.

The same bug exists in `_inject_into_coverage_py()` (plugin.py:324) — it also calls `add_lines()` before `add_arcs()`.

## Key Insight

Coverage.py derives line coverage **from arcs**. Any line that appears as a source or destination in an arc is considered executed. For example, the arcs coverage.py records for our test file look like:

```
[(-5, 6), (-1, 1), (-1, 2), (1, 5), (2, -1), (5, 11), (6, 7), (7, -5), (11, -1)]
```

Where negative numbers represent function entry/exit:
- `(-1, 1)` = module entry to line 1
- `(2, -1)` = line 2 exits to module-level
- `(-5, 6)` = entry to function defined at line 5 (partially_covered), first body line is 6
- `(7, -5)` = line 7 exits the function defined at line 5

From these arcs alone, coverage.py knows lines 1, 2, 5, 6, 7, 11 were executed.

The current `_compute_arcs()` only produces **branch arcs** (if/for/while true/false destinations). It doesn't produce the sequential execution arcs that coverage.py needs to derive line coverage. That's why, even when `add_arcs()` runs, only partial line coverage appears.

## Solution

When coverage.py is in arc mode, **skip `add_lines()` entirely** and instead generate comprehensive execution arcs that encode all line-to-line transitions. These must include:

1. **Sequential arcs** `(line_N, line_M)` for consecutive executed lines within the same scope
2. **Function entry arcs** `(-func_def_line, first_body_line)` for each executed function
3. **Function exit arcs** `(last_executed_line, -func_def_line)` for returns
4. **Module entry arcs** `(-1, first_module_line)` for module-level code
5. **Branch arcs** (already produced by `_compute_arcs()`)

When coverage.py is NOT in arc mode (line-only mode), keep using `add_lines()` as today.

### Changes needed

**1. `plugin.py` — `_save_with_injection()` and `_inject_into_coverage_py()`**

Check `data.has_arcs()` before choosing the injection strategy:

```python
data = cov.get_data()
if data.has_arcs():
    # Branch mode: provide everything via add_arcs() — coverage.py
    # derives line coverage from arcs automatically.
    arcs = compute_full_arcs_for_store(plugin._store)
    if arcs:
        data.add_arcs(arcs)
else:
    # Line-only mode: add_lines() works fine.
    data.add_lines(plugin._store.lines_by_file())
```

**2. `reporters/report_data.py` — new `_compute_full_arcs()` function**

A new function that, for each file in the store, uses AST + execution data to produce the full set of arcs coverage.py expects. This is different from `_compute_arcs()` which only handles branch arcs.

The algorithm for a single file:

```
Parse the AST.
Build a map: function_def_line -> list of executed lines within that function.
Build module-level executed lines list.

For module-level lines (sorted):
    Emit (-1, first_line)                          # module entry
    Emit (line_i, line_i+1) for consecutive pairs  # sequential
    Emit function entry arcs where def lines appear # transitions into functions

For each function (sorted by def line):
    Emit (-def_line, first_body_line)              # function entry
    Emit (line_i, line_i+1) for consecutive pairs  # sequential within function
    Emit (last_line, -def_line)                    # function exit (return)

Add branch arcs from existing _compute_arcs().
```

The tricky part is correctly assigning executed lines to their enclosing function scope. This can be done by walking the AST and building a `line -> enclosing function def line` map.

**3. Expose as `compute_full_arcs_for_store()`** — wrapper analogous to `compute_arcs_for_store()`.

### Why this works

- Coverage.py derives `covered_lines` by extracting all line numbers from arc endpoints
- Coverage.py derives `covered_branches` by comparing executed arcs against `arc_possibilities()` (computed from its own AST analysis)
- By providing comprehensive execution arcs, coverage.py can reconstruct both line and branch coverage accurately

### Edge cases to handle

- **Empty functions / pass-only bodies**: Still need entry/exit arcs
- **Multi-line statements**: The AST lineno is the first line; coverage.py handles this
- **Decorators**: `def` line vs decorator line — use the AST node's `lineno` (which is the `def` keyword line) for the negative function ID, matching coverage.py's convention
- **Class bodies**: Similar to module-level — class definition creates a scope
- **Nested functions**: Each has its own entry/exit arcs with its own def line

### Testing

The existing `test_coverage_py_and_coverage_stats_agree_on_total_coverage` test should pass after this fix. Consider adding:
- A test with line-only mode (`--cov` without `--cov-branch`) to verify the `add_lines()` path still works
- A test with more complex branching (nested if, for loops, early returns)

## Files to change

| File | Change |
|---|---|
| `src/coverage_stats/plugin.py` | In both `_save_with_injection()` and `_inject_into_coverage_py()`: check `data.has_arcs()` and branch between `add_arcs()`-only vs `add_lines()` |
| `src/coverage_stats/reporters/report_data.py` | Add `_compute_full_arcs()` that generates comprehensive execution arcs (sequential + entry/exit + branch), and `compute_full_arcs_for_store()` wrapper |
