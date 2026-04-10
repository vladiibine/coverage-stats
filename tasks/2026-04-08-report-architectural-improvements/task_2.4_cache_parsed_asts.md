# Task 2.4 — Cache parsed ASTs across reporting phase

**Priority:** P2
**Effort:** Medium
**Impact:** Medium (perf for reporting phase)
**Status:** Done

## Problem

The same source file is parsed with `ast.parse` up to three times during a single reporting run:

1. `get_executable_lines(path)` in `executable_lines.py` — reads and parses to find executable statements
2. `DefaultReportBuilder._analyze_branches(path, lines)` in `report_data.py` — reads and parses again for branch analysis
3. `CoveragePyInterop.compute_arcs(path, lines)` in `report_data.py` — reads and parses a third time for arc computation

For a file with 1,000 lines, `ast.parse` takes ~1–5 ms. Across 100 files with all three callers active, that's 300–1,500 ms of redundant file I/O and parsing during the reporting phase.

## Solution

### Option A: Session-scoped AST cache (simpler)

Introduce a `dict[str, ast.Module]` cache passed through the report builder:

```python
class DefaultReportBuilder:
    def build(self, store, config):
        _ast_cache: dict[str, ast.Module] = {}
        ...
        branch_analysis = self._analyze_branches(abs_path, line_data, _ast_cache)
        executable = get_executable_lines(abs_path, ast_cache=_ast_cache)
        ...
```

Update `get_executable_lines` to accept an optional cache:
```python
def get_executable_lines(path: str, ast_cache: dict | None = None) -> set[int]:
    if ast_cache is not None and path in ast_cache:
        tree = ast_cache[path]
    else:
        source = open(path).read()
        tree = ast.parse(source)
        if ast_cache is not None:
            ast_cache[path] = tree
    ...
```

### Option B: `FileAnalysis` object (cleaner, more extensible)

Combine all per-file analysis into a single object that parses once:

```python
@dataclass
class FileAnalysis:
    path: str
    tree: ast.Module
    source_lines: list[str]
    executable_lines: set[int]
    
    @classmethod
    def from_path(cls, path: str) -> FileAnalysis:
        source = Path(path).read_text()
        tree = ast.parse(source)
        return cls(
            path=path,
            tree=tree,
            source_lines=source.splitlines(),
            executable_lines=_compute_executable(tree),
        )
```

`DefaultReportBuilder` creates a `FileAnalysis` per file and passes it to both `_analyze_branches` and `get_executable_lines`. `CoveragePyInterop.compute_arcs` can accept a `FileAnalysis` too.

Option B is preferred if task 3.2 (deduplicate branch walking) is also done — a shared `FileAnalysis` becomes the natural place to cache the branch walk results as well.
