# Plan: Partial Coverage for Match Statements

## What Coverage.py Actually Does (verified)

From the HTML output of coverage.py on a match statement where only `case 1:` was taken:

| Line | CSS class | Meaning |
|------|-----------|---------|
| `match value:` | `run` | Just covered — **not** marked partial |
| `case 1:` | **`par`** | **Partial** — annotation: "line 102 didn't jump to line 104 because the pattern on line 102 always matched" |
| `return "one"` | `run` | Covered |
| `case 2:` | `mis` | Missing (never reached) |
| `return "two"` | `mis` | Missing |
| `case _:` | `mis` | Missing (never reached) |

**The partial marking lands on `case` pattern lines, not on `match`.**

Coverage.py creates one arc per case: from the previous case (or match) to the next case
("the pattern always matched"). A case line is partial when it was reached but didn't take
all its exits: either the "matched" branch (to body) or the "didn't match" branch (to next case).

---

## Analysis

### Case line as branch point

For a non-last `case X:` at `case_line`, there are two exits:
1. **Matched** → `body[0].lineno` (body first line)
2. **Didn't match** → `next_case.pattern.lineno` (next case pattern line)

Partial condition (non-last case):
- `count(case_line) > 0` AND (`count(body[0].lineno) == 0` OR `count(next_case.pattern.lineno) == 0`)

For the **last case** at `case_line`:
- Only one detectable exit: the "matched" → `body[0].lineno`
- Partial condition: `count(case_line) > 0` AND `count(body[0].lineno) == 0`

### Case lines and executable_lines

`ast.match_case` is NOT an `ast.stmt` subclass, so `get_executable_lines()` currently skips
case pattern lines. Without fixing this:
- Case lines won't appear as covered/missing in the HTML (rendered as plain text)
- `partial_branches & executable` will always exclude case lines → `partial_cnt` stays 0

**`executable_lines.py` must be updated** to include case pattern lines.

### Python version concern

`ast.Match` only exists in Python 3.10+. Runtime guard: `sys.version_info >= (3, 10)`.
Mypy targets `python_version = "3.10"` so no type-ignore needed.

---

## Changes

### 1. `src/coverage_stats/executable_lines.py`

After the existing `ast.walk` loop, add case pattern lines for match statements (Python 3.10+):

```python
import sys

if sys.version_info >= (3, 10):
    for node in ast.walk(tree):
        if isinstance(node, ast.Match):
            for case in node.cases:
                result.add(case.pattern.lineno)
```

### 2. `src/coverage_stats/reporters/html.py`

**Modify `_get_partial_branches()`**: add `ast.Match` handling that marks case pattern lines
(not the match line) as partial.

```python
if sys.version_info >= (3, 10):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Match):
            continue
        for i, case in enumerate(node.cases):
            case_line = case.pattern.lineno
            if _count(case_line) == 0:
                continue  # missing, not partial
            body_taken = _count(case.body[0].lineno) > 0
            if i < len(node.cases) - 1:
                next_case_taken = _count(node.cases[i + 1].pattern.lineno) > 0
                if not body_taken or not next_case_taken:
                    result.add(case_line)
            else:
                # Last case: only check body was taken
                if not body_taken:
                    result.add(case_line)
```

Also update the docstring to mention match statements and that partial marks case lines.

**Also add `import sys`** at the top of html.py if not already present.

### 3. `tests/unit/test_reporters/test_partial_branches.py` (new file)

Direct unit tests for `_get_partial_branches`. Uses real source files in `tmp_path` with
match statements, and manually-set `LineData` counts.

Tests:
- `test_match_case1_always_matched_is_partial` — case 1 always matched, case 2 never tried → case 1 line is partial
- `test_match_all_cases_taken_not_partial` — all cases entered at least once → no case line is partial
- `test_match_case_never_reached_not_partial` — case line count 0 → not partial (missing)
- `test_match_case_never_matched_is_partial` — case was reached but body never ran → case line is partial
- `test_match_last_case_not_taken_is_partial` — last case reached but body never ran → partial
- `test_match_last_case_taken_not_partial` — last case reached and body ran → not partial

Also add tests for `get_executable_lines`:
- `test_match_case_lines_are_executable` — case pattern lines included in executable set

### 4. `coverage-stats-example/src/asdf.py`

`weird_corner_cases_5_match` is already added (from investigation). Keep it.

### 5. `coverage-stats-example/tests/test_asdf.py`

`test_weird_corner_cases_5` is already added (from investigation). It only calls with
`value=1`, so `case 2:` and `case _:` are never reached. This causes `case 1:` to show as
partial (always matched, never fell through).

---

## Execution Order

1. Update `executable_lines.py`
2. Update `reporters/html.py`
3. Add unit tests
4. Run tests: `uv run pytest tests/`
5. Run mypy: `uv run mypy src/`

## Non-goals
- No changes to profiler, store, or covers
- No changes to JSON/CSV reporters
- No handling of match guards (`if` on a case) beyond what the line-count heuristic catches
- No handling of the "last non-wildcard case never matched" arc (coverage.py adds this only
  when there's no wildcard; detecting wildcard patterns requires extra AST inspection that
  adds complexity for a rare edge case — can be added later)
