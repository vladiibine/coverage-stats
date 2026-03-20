# Plan: Total Coverage Matching coverage.py (with branch arcs)

## Root Cause

Coverage.py's "Cover" percentage (when run with `--cov-branch`) uses the formula:

```
(stmts_covered + arcs_covered) / (stmts_total + arcs_total) * 100
```

Coverage-stats currently uses statement-only coverage:

```
stmts_covered / stmts_total * 100
```

For `asdf.py`: coverage.py reports 74%, coverage-stats reports 78%. Both agree on
statements (59 total, 13 missed, 46 covered). The difference is branch arcs.

**Verified:** with arcs_total=14, arcs_covered=8 → (46+8)/(59+14) = 54/73 = **74.0%** ✓

---

## Arc Counting Rules

For each branch statement type, regardless of whether it was executed:

### `ast.If`, `ast.While`, `ast.For`
- **arcs_total += 2** (true branch and false branch)
- **arcs_covered**: same as in `_get_partial_branches` — 1 for true if body was taken,
  1 for false if false branch was taken

### `ast.Match` — per `case`:
- **Non-last case**: arcs_total += 2 (matched → body, not matched → next case)
  - arcs_covered: 1 if body was taken, 1 if next case was reached
- **Last case, wildcard** (`MatchAs` with no pattern, no guard): arcs_total += 0
  (wildcard always matches — no branching)
- **Last case, non-wildcard**: arcs_total += 1 (only the "matched" arc; the
  "no match falls through" exit is not detectable with line counts alone)
  - arcs_covered: 1 if body was taken

Branch statements that were **never executed** (count == 0) still contribute
arcs_total but 0 arcs_covered — coverage.py counts their arcs as missed.

---

## Wildcard Detection

Copy coverage.py's exact logic (from `parser.py`):
```python
def _is_wildcard_case(case: ast.match_case) -> bool:
    pattern = case.pattern
    while isinstance(pattern, ast.MatchOr):
        pattern = pattern.patterns[-1]
    while isinstance(pattern, ast.MatchAs) and pattern.pattern is not None:
        pattern = pattern.pattern
    return isinstance(pattern, ast.MatchAs) and pattern.pattern is None and case.guard is None
```

---

## Changes

### 1. `src/coverage_stats/reporters/html.py`

#### 1a. Replace `_get_partial_branches()` with `_analyze_branches()`

Combine partial detection and arc counting into one function (avoids parsing the
AST twice):

```python
@dataclass
class _BranchAnalysis:
    partial: set[int]    # line numbers with partial branch coverage
    arcs_total: int      # total branch arc count
    arcs_covered: int    # branch arcs that were taken

def _analyze_branches(path: str, lines: dict[int, LineData]) -> _BranchAnalysis:
    ...
```

The logic inside mirrors the current `_get_partial_branches` exactly, but also
accumulates `arcs_total` and `arcs_covered` as it goes.

#### 1b. Update `_write_file_page()`

Replace:
```python
partial_branches = _get_partial_branches(abs_path, lines)
partial_cnt = len(partial_branches & executable)
total_pct = covered_stmts / total_stmts * 100.0 if total_stmts else 0.0
```
With:
```python
branch_analysis = _analyze_branches(abs_path, lines)
partial_cnt = len(branch_analysis.partial & executable)
total_pct = (
    (covered_stmts + branch_analysis.arcs_covered) /
    (total_stmts + branch_analysis.arcs_total) * 100.0
    if (total_stmts + branch_analysis.arcs_total) else 0.0
)
```

#### 1c. Update `_FileEntry` — add `arcs_total` and `arcs_covered`

```python
@dataclass
class _FileEntry:
    rel_path: str
    file_html_name: str
    total_stmts: int
    total_covered: int
    arcs_total: int       # ← new
    arcs_covered: int     # ← new
    deliberate_covered: int
    incidental_covered: int
```

#### 1d. Update `_FolderNode` — add `agg_arcs_total()` and `agg_arcs_covered()`

```python
def agg_arcs_total(self) -> int:
    return sum(f.arcs_total for f in self.files) + sum(
        s.agg_arcs_total() for s in self.subfolders.values()
    )

def agg_arcs_covered(self) -> int:
    return sum(f.arcs_covered for f in self.files) + sum(
        s.agg_arcs_covered() for s in self.subfolders.values()
    )
```

#### 1e. Update `write_html()` — compute arcs per file

Add alongside the existing per-file computation:
```python
branch_analysis = _analyze_branches(abs_path, lines)
arcs_total = branch_analysis.arcs_total
arcs_covered = branch_analysis.arcs_covered
total_covered = sum(
    1 for ln in executable
    if ln in lines and (lines[ln].deliberate_executions > 0 or lines[ln].incidental_executions > 0)
)
```
Pass `arcs_total` and `arcs_covered` to `_FileEntry`.

#### 1f. Update `_render_tree_rows()`

Replace `total_pct = entry.total_covered / total * 100.0` with:
```python
total_denom = total + entry.arcs_total
total_pct = (entry.total_covered + entry.arcs_covered) / total_denom * 100.0 if total_denom else 0.0
```
Same for folder rows using `sub.agg_arcs_total()` and `sub.agg_arcs_covered()`.

---

### 2. Tests

#### Existing tests to update
- Any test constructing `_FileEntry` directly — add `arcs_total` and `arcs_covered` args
- `test_folder_node_aggregates_stats` — add assertions for `agg_arcs_total/covered`
- `test_render_tree_rows_pct_calculation` — update expected total % value
- `test_render_tree_rows_total_pct_column` — update expected total % value
- `test_folder_node_agg_total_covered` — add arcs fields to `_FileEntry` calls

#### New tests to add

In `tests/unit/test_reporters/test_partial_branches.py`:
- `test_analyze_branches_if_both_taken` — no partial, arcs_total=2, arcs_covered=2
- `test_analyze_branches_if_false_not_taken` — partial, arcs_total=2, arcs_covered=1
- `test_analyze_branches_for_body_not_taken` — partial, arcs_total=2, arcs_covered=1
- `test_analyze_branches_match_wildcard_last_case` — wildcard contributes 0 arcs
- `test_analyze_branches_match_non_wildcard_last_case` — contributes 1 arc
- `test_analyze_branches_unreached_branch_contributes_missed_arcs` — if_count=0 → arcs_total+=2, arcs_covered+=0

---

## Execution Order

1. Add `_BranchAnalysis` dataclass and `_analyze_branches()` (replacing `_get_partial_branches`)
2. Update `_write_file_page()` to use arc-adjusted `total_pct`
3. Update `_FileEntry` with `arcs_total`, `arcs_covered` fields
4. Update `_FolderNode` with `agg_arcs_total()`, `agg_arcs_covered()`
5. Update `write_html()` to compute and pass arc counts
6. Update `_render_tree_rows()` to use arc-adjusted total %
7. Update and add tests
8. `uv run pytest tests/`
9. `uv run mypy src/`

---

## Known Limitation

The arc count will match coverage.py for `if`/`while`/`for`/`match`. It will **not**
account for `try`/`except`/`else`/`finally` blocks, which coverage.py also treats as
branch points. Those are not currently handled by coverage-stats at all, so any
discrepancy from `try` blocks is pre-existing and out of scope for this task.
