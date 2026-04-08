# Task 3.1 — Make branch analysis pluggable via `BranchAnalyzer` protocol

**Priority:** P3
**Effort:** Medium
**Impact:** Medium (extensibility)

## Problem

Branch analysis is a protected method on `DefaultReportBuilder`. Users who want different branch semantics — e.g., counting `try/except`, `with` statements, comprehension short-circuits, or generator `yield` as branches — must subclass `DefaultReportBuilder` and override the entire 110-line `_analyze_branches` method.

This is impractical: the method is long, interleaves if/while/for logic with match-case logic, and any override must duplicate the parts the user doesn't want to change. There is no way to extend branch analysis incrementally (e.g., "add `try/except` support on top of the existing rules").

## Solution

Extract branch analysis into a `BranchAnalyzer` protocol with a default implementation:

```python
class BranchAnalyzer(Protocol):
    def analyze(
        self,
        path: str,
        lines: dict[int, LineData],
    ) -> _BranchAnalysis: ...

class DefaultBranchAnalyzer:
    """Default implementation: if/while/for + match-case."""

    def analyze(self, path, lines):
        tree = self._parse(path)
        if tree is None:
            return _BranchAnalysis(partial=set(), arcs_total=0, arcs_covered=0,
                                   arcs_deliberate=0, arcs_incidental=0)
        partial: set[int] = set()
        counters = _ArcCounters()
        self._analyze_if_while_for(tree, lines, partial, counters)
        self._analyze_match(tree, lines, partial, counters)
        return _BranchAnalysis(partial=partial, **counters.as_dict())

    def _analyze_if_while_for(self, tree, lines, partial, counters): ...
    def _analyze_match(self, tree, lines, partial, counters): ...
    def _parse(self, path: str) -> ast.Module | None: ...
```

Add `branch_analyzer` to `CoverageStatsCustomization`:

```python
class CoverageStatsCustomization:
    branch_analyzer = "coverage_stats.reporters.branch_analysis.DefaultBranchAnalyzer"

    def get_branch_analyzer(self) -> BranchAnalyzer:
        return self._load_class(self.branch_analyzer)()
```

`DefaultReportBuilder._analyze_branches` delegates to `self._branch_analyzer.analyze(path, lines)`, where `_branch_analyzer` is injected at construction time.

**Prerequisites:** Task 3.2 (deduplicate branch walking) should be done first — the shared `BranchDescriptor` model makes it easy to compose analyzers.

**Extension example:** A user who wants to add `try/except` branch support subclasses `DefaultBranchAnalyzer` and overrides only `_analyze_try_except`:

```python
class ExtendedBranchAnalyzer(DefaultBranchAnalyzer):
    def analyze(self, path, lines):
        result = super().analyze(path, lines)
        # Add try/except arcs on top
        ...
        return result
```
