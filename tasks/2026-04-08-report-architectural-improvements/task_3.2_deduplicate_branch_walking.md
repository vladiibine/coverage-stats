# Task 3.2 — Deduplicate branch-walking between report builder and coverage.py interop

**Priority:** P2
**Effort:** Medium
**Impact:** Medium (maintainability)

## Problem

`DefaultReportBuilder._analyze_branches` and `CoveragePyInterop.compute_arcs` both walk the AST for `if/while/for/match` nodes with nearly identical logic. They diverge only in what they produce:

- `_analyze_branches`: counts arcs (total/covered/deliberate/incidental), detects partial coverage
- `compute_arcs`: produces `(from_line, to_line)` arc pairs for coverage.py injection

Current duplication: ~110 lines in `_analyze_branches` and ~80 lines in `compute_arcs` share the same `if/while/for` traversal pattern, the same `match` wildcard detection (`_is_wildcard_case`), and the same execution-count heuristics. Any bug fixed in one must be manually applied to the other.

## Solution

Extract a shared `BranchWalker` that yields `BranchDescriptor` objects, one per branch node:

```python
@dataclass
class BranchDescriptor:
    node_line: int
    true_target: int          # line number of true-branch first statement
    false_target: int | None  # line number of false-branch, or None if no else
    true_taken: bool
    false_taken: bool
    deliberate_true: bool
    deliberate_false: bool
    incidental_true: bool
    incidental_false: bool
```

```python
def walk_branches(
    tree: ast.Module,
    lines: dict[int, LineData],
) -> Iterator[BranchDescriptor]:
    """Yield one BranchDescriptor per branch node (if/while/for/match case)."""
    ...
```

Both consumers then iterate over descriptors and interpret them differently:

```python
# In _analyze_branches:
for bd in walk_branches(tree, lines):
    arcs_total += 2  # or 1 for last match case
    arcs_covered += (1 if bd.true_taken else 0) + (1 if bd.false_taken else 0)
    arcs_deliberate += (1 if bd.deliberate_true else 0) + ...
    if not bd.true_taken or not bd.false_taken:
        partial.add(bd.node_line)

# In compute_arcs:
for bd in walk_branches(tree, lines):
    if bd.true_taken:
        arcs.append((bd.node_line, bd.true_target))
    if bd.false_taken and bd.false_target is not None:
        arcs.append((bd.node_line, bd.false_target))
```

This eliminates ~60 lines of duplicated AST walking and ensures both consumers always stay in sync when branch semantics change (e.g., adding `try/except` support).

**Natural pairing with task 1.2:** Move `walk_branches` to `reporters/branch_analysis.py` so it is shared without introducing a circular import.

**Natural pairing with task 3.1:** If branch analysis becomes pluggable, `walk_branches` is the thing users would override — making it a separate function is the right prerequisite.
