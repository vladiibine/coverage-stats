# Plan: Track Deliberate/Incidental Coverage Per Arc

## Goal

Make deliberate % and incidental % use the same denominator as total %, so all
three metrics are expressed on the same scale.

**Important:** deliberate % + incidental % do NOT need to sum to total %, and
in general they will not. Example: a codebase with a single function where one
incidental test covers all lines and one deliberate test also covers all lines
would yield deliberate = 100%, incidental = 100%, total = 100%. The overlap is
expected and correct — deliberate and incidental are independent measurements
of the same code, not disjoint partitions of it.

The problem being fixed is purely one of scale: currently deliberate/incidental
divide by `stmts_total` while total divides by `stmts_total + arcs_total`, so
the three numbers are not directly comparable. The fix is to give all three the
same denominator.

Current formulae:
```
total %       = (stmts_covered + arcs_covered)     / (stmts_total + arcs_total)
deliberate %  = deliberate_stmts                   / stmts_total          ← different scale
incidental %  = incidental_stmts                   / stmts_total          ← different scale
```

Target formulae:
```
total %       = (stmts_covered    + arcs_covered)    / (stmts_total + arcs_total)
deliberate %  = (deliberate_stmts + arcs_deliberate) / (stmts_total + arcs_total)
incidental %  = (incidental_stmts + arcs_incidental) / (stmts_total + arcs_total)
```

---

## Arc Attribution Rules

An arc is **deliberate** if the line that witnesses it being taken has
`deliberate_executions > 0`; **incidental** if `incidental_executions > 0`.
(These are not mutually exclusive — a line can be both.)

### `if` / `for` / `while` — true arc

Witness line: `node.body[0].lineno`

```
del_true  = deliberate_executions[body[0]] > 0
inc_true  = incidental_executions[body[0]] > 0
```

### `if` / `for` — false arc, with `orelse`

Witness line: `node.orelse[0].lineno`

```
del_false = deliberate_executions[orelse[0]] > 0
inc_false = incidental_executions[orelse[0]] > 0
```

### `if` / `for` / `while` — false arc, without `orelse`

The false arc is taken whenever the condition evaluated to False, i.e. the
condition line ran more times than the body's first line.

```
del_false = del_count(node.lineno) > del_count(body[0].lineno)
inc_false = inc_count(node.lineno) > inc_count(body[0].lineno)
```

Where `del_count` / `inc_count` read `deliberate_executions` /
`incidental_executions` from `lines`, defaulting to 0.

### `match` — non-last case, arc 1 (body taken)

Witness line: `case.body[0].lineno`

```
del = deliberate_executions[body[0]] > 0
inc = incidental_executions[body[0]] > 0
```

### `match` — non-last case, arc 2 (next case reached)

Witness line: `next_case.pattern.lineno`

```
del = deliberate_executions[next_case.pattern] > 0
inc = incidental_executions[next_case.pattern] > 0
```

### `match` — last non-wildcard case (body taken)

Witness line: `case.body[0].lineno` (same as arc 1 above)

### `match` — last wildcard case

Contributes 0 arcs — no change.

### Unreached branches (node never executed)

`arcs_deliberate += 0`, `arcs_incidental += 0` — same as today for
`arcs_covered`.

---

## Changes

### 1. `src/coverage_stats/reporters/html.py`

#### 1a. Extend `_BranchAnalysis`

```python
@dataclass
class _BranchAnalysis:
    partial: set[int]
    arcs_total: int
    arcs_covered: int
    arcs_deliberate: int   # ← new
    arcs_incidental: int   # ← new
```

#### 1b. Extend `_analyze_branches()`

Add `_del_count` and `_inc_count` helpers alongside the existing `_count`:

```python
def _del_count(lineno: int) -> int:
    ld = lines.get(lineno)
    return ld.deliberate_executions if ld else 0

def _inc_count(lineno: int) -> int:
    ld = lines.get(lineno)
    return ld.incidental_executions if ld else 0
```

For each arc that is currently counted in `arcs_covered`, also check
`del_count` / `inc_count` on the witness line and increment
`arcs_deliberate` / `arcs_incidental` accordingly (using the attribution
rules above).

#### 1c. Extend `_FileEntry`

```python
@dataclass
class _FileEntry:
    rel_path: str
    file_html_name: str
    total_stmts: int
    total_covered: int
    arcs_total: int
    arcs_covered: int
    arcs_deliberate: int   # ← new
    arcs_incidental: int   # ← new
    deliberate_covered: int
    incidental_covered: int
```

#### 1d. Extend `_FolderNode`

```python
def agg_arcs_deliberate(self) -> int:
    return sum(f.arcs_deliberate for f in self.files) + sum(
        s.agg_arcs_deliberate() for s in self.subfolders.values()
    )

def agg_arcs_incidental(self) -> int:
    return sum(f.arcs_incidental for f in self.files) + sum(
        s.agg_arcs_incidental() for s in self.subfolders.values()
    )
```

#### 1e. Update `write_html()`

Pass `arcs_deliberate` and `arcs_incidental` from `branch_analysis` to
`_FileEntry`.

#### 1f. Update `_write_file_page()`

```python
deliberate_pct = (
    (deliberate_covered + branch_analysis.arcs_deliberate) /
    total_denom * 100.0 if total_denom else 0.0
)
incidental_pct = (
    (incidental_covered + branch_analysis.arcs_incidental) /
    total_denom * 100.0 if total_denom else 0.0
)
```

#### 1g. Update `_render_tree_rows()`

For both folder and file rows, replace:
```python
delib_pct = delib / total * 100.0
incid_pct = incid / total * 100.0
```
With:
```python
delib_pct = (delib + arcs_deliberate) / total_denom * 100.0 if total_denom else 0.0
incid_pct = (incid + arcs_incidental) / total_denom * 100.0 if total_denom else 0.0
```

Where:
- For file rows: `arcs_deliberate = entry.arcs_deliberate`, `arcs_incidental = entry.arcs_incidental`
- For folder rows: `arcs_deliberate = sub.agg_arcs_deliberate()`, `arcs_incidental = sub.agg_arcs_incidental()`

---

### 2. Tests

#### Existing tests to update

- All `_FileEntry(...)` calls — add `arcs_deliberate=0, arcs_incidental=0` args
- `test_folder_node_aggregates_stats` — add assertions for new aggregation methods
- `test_render_tree_rows_pct_calculation` — update expected deliberate/incidental % (they now divide by stmts+arcs)
- `test_render_tree_rows_total_pct_column` — same

#### New tests to add (in `test_partial_branches.py`)

- `test_analyze_branches_if_true_arc_deliberate` — body run deliberately → `arcs_deliberate=1`
- `test_analyze_branches_if_true_arc_incidental` — body run incidentally → `arcs_incidental=1`
- `test_analyze_branches_if_false_arc_no_orelse_deliberate` — condition evaluated more times than body during deliberate tests
- `test_analyze_branches_if_both_arcs_deliberate_and_incidental` — same arc taken in both kinds of tests
- `test_analyze_branches_match_arc_deliberate` — match body taken deliberately

---

## Execution Order

1. Extend `_BranchAnalysis` and `_analyze_branches()` with arc attribution
2. Extend `_FileEntry` and `_FolderNode`
3. Update `write_html()` to pass new arc fields
4. Update `_write_file_page()` to use arc-adjusted deliberate/incidental pct
5. Update `_render_tree_rows()` to use arc-adjusted deliberate/incidental pct
6. Update existing tests
7. Add new tests
8. `uv run pytest tests/`
9. `uv run mypy src/`
