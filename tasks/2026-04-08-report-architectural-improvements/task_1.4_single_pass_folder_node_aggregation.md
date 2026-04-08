# Task 1.4 — Single-pass `FolderNode` aggregation

**Priority:** P1
**Effort:** Low
**Impact:** Medium (perf for large codebases)

## Problem

`FolderNode` has 9 `agg_*` methods that each recursively traverse the entire subtree independently:

```python
def agg_total_stmts(self) -> int:
    return sum(f.total_stmts for f in self.files) + sum(
        s.agg_total_stmts() for s in self.subfolders.values()
    )

def agg_total_covered(self) -> int: ...
def agg_arcs_total(self) -> int: ...
# ... 6 more
```

`to_index_row()` calls all 9 of them. For a folder tree with 50 folders and an average depth of 3, rendering the index page performs ~450 separate recursive traversals (9 metrics × 50 nodes × average subtree size). This is O(n·d·k) where n = files, d = depth, k = 9 metrics.

## Solution

Introduce a `_FolderAggregates` dataclass and compute all 9 values in a single bottom-up pass, cached on the node after the tree is built:

```python
@dataclass
class _FolderAggregates:
    total_stmts: int = 0
    total_covered: int = 0
    arcs_total: int = 0
    arcs_covered: int = 0
    arcs_deliberate: int = 0
    arcs_incidental: int = 0
    deliberate: int = 0
    incidental: int = 0
    incidental_asserts: int = 0
    deliberate_asserts: int = 0

@dataclass
class FolderNode:
    path: str
    subfolders: dict[str, FolderNode] = field(default_factory=dict)
    files: list[FileSummary] = field(default_factory=list)
    _agg: _FolderAggregates | None = field(default=None, repr=False, compare=False)

    def compute_aggregates(self) -> _FolderAggregates:
        if self._agg is not None:
            return self._agg
        agg = _FolderAggregates()
        for f in self.files:
            agg.total_stmts += f.total_stmts
            agg.total_covered += f.total_covered
            # ... all fields
        for sub in self.subfolders.values():
            sub_agg = sub.compute_aggregates()
            agg.total_stmts += sub_agg.total_stmts
            # ... all fields
        self._agg = agg
        return agg
```

Call `root.compute_aggregates()` (or each node's) once after `build_folder_tree()` returns. Replace all 9 `agg_*` methods with reads from `_agg`.

`to_index_row()` becomes a simple read from the cached `_agg`, reducing index rendering from O(n·d·k) to O(n).
