# Task 1.2 — Break up `report_data.py`

**Priority:** P1
**Effort:** Medium
**Impact:** High (maintainability)

## Problem

`reporters/report_data.py` is 758 lines and combines four unrelated concerns:

1. **Dataclasses** (`LineReport`, `FileSummary`, `IndexRowData`, `FolderNode`, `FileReport`, `CoverageReport`, `_BranchAnalysis`) — consumed by all reporters, but buried inside a module named after report-building.
2. **`DefaultReportBuilder`** — builds `CoverageReport` from `SessionStore`; contains `_analyze_branches` (110 lines of AST walking).
3. **`CoveragePyInterop`** — computes arc data and patches `coverage.save()`; an entirely separate concern from report building.
4. **Backward-compat shims** at module level (`build_report`, `build_folder_tree`, `_analyze_branches` as free functions) — referenced only by tests; should not exist in library code (there's even a TODO comment about this at line 745).

The duplication between `_analyze_branches` (in `DefaultReportBuilder`) and `compute_arcs` (in `CoveragePyInterop`) is only visible because they share a file — it's a symptom of poor separation.

## Solution

Split into four focused modules:

### `reporters/models.py`
All dataclasses: `LineReport`, `FileSummary`, `IndexRowData`, `FolderNode`, `FileReport`, `CoverageReport`, `_BranchAnalysis`. These are the shared vocabulary for the entire reporters package. Moving them here makes it obvious they are data, not behavior.

### `reporters/branch_analysis.py`
Shared AST branch-walking logic extracted from both `DefaultReportBuilder._analyze_branches` and `CoveragePyInterop.compute_arcs`. Both currently duplicate ~60 lines of `if/while/for/match` traversal. A `BranchWalker` or a `BranchDescriptor`-yielding function can serve both consumers. (See also task 3.2.)

### `reporters/report_data.py` (slimmed down)
`DefaultReportBuilder` only — `build()`, `build_folder_tree()`, `_analyze_branches()` now delegating to `branch_analysis.py`. Remove the three shim functions at the bottom.

### `reporters/coverage_py_interop.py`
`CoveragePyInterop` and `CoveragePyInteropProto` moved here. This keeps all the coverage.py patching logic in one place, separate from report building. The `ReportBuilder` protocol can stay in `report_data.py` or move to `base.py`.

**Migration steps:**
1. Create `models.py`, move dataclasses, update all imports.
2. Create `coverage_py_interop.py`, move `CoveragePyInterop` and its protocol, update imports in `plugin.py` and `report_data.py`.
3. Create `branch_analysis.py` (or defer to task 3.2).
4. Delete the three shim functions from `report_data.py`; update the test files that import them to import from `DefaultReportBuilder` directly.
5. Update import-linter contracts if needed.
