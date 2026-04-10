from __future__ import annotations

import ast
from dataclasses import dataclass, field


def _is_wildcard_case(case: ast.match_case) -> bool:
    """Mirror coverage.py's wildcard detection logic for match-case statements."""
    pattern = case.pattern
    while isinstance(pattern, ast.MatchOr):
        pattern = pattern.patterns[-1]
    while isinstance(pattern, ast.MatchAs) and pattern.pattern is not None:
        pattern = pattern.pattern
    return isinstance(pattern, ast.MatchAs) and pattern.pattern is None and case.guard is None


@dataclass
class _BranchAnalysis:
    partial: set[int]    # line numbers with partial branch coverage
    arcs_total: int      # total branch arc count
    arcs_covered: int    # branch arcs that were taken
    arcs_deliberate: int # branch arcs taken during deliberate tests
    arcs_incidental: int # branch arcs taken during incidental tests


@dataclass
class LineReport:
    lineno: int
    source_text: str
    executable: bool
    partial: bool
    incidental_executions: int
    deliberate_executions: int
    incidental_asserts: int
    deliberate_asserts: int
    incidental_tests: int
    deliberate_tests: int


@dataclass
class IndexRowData:
    """All values needed to render one row on the index page.

    Produced by ``FileSummary.to_index_row()`` and ``FolderNode.to_index_row()``;
    ``HtmlReporter._render_tree_rows`` only formats, never computes.
    """
    total_stmts: int
    total_pct: float
    deliberate_pct: float
    incidental_pct: float
    deliberate_covered: int
    incidental_covered: int
    incidental_asserts: int
    deliberate_asserts: int
    inc_assert_density: float   # incidental_asserts / (stmts + arcs), 0.0 when denom=0
    del_assert_density: float   # deliberate_asserts  / (stmts + arcs), 0.0 when denom=0


@dataclass
class FileSummary:
    rel_path: str
    abs_path: str
    total_stmts: int
    total_covered: int
    deliberate_covered: int
    incidental_covered: int
    arcs_total: int
    arcs_covered: int
    arcs_deliberate: int
    arcs_incidental: int
    total_pct: float
    deliberate_pct: float
    incidental_pct: float
    partial_count: int
    incidental_asserts: int = 0
    deliberate_asserts: int = 0

    def to_index_row(self) -> IndexRowData:
        denom = self.total_stmts + self.arcs_total
        return IndexRowData(
            total_stmts=denom,
            total_pct=self.total_pct,
            deliberate_pct=self.deliberate_pct,
            incidental_pct=self.incidental_pct,
            deliberate_covered=self.deliberate_covered,
            incidental_covered=self.incidental_covered,
            incidental_asserts=self.incidental_asserts,
            deliberate_asserts=self.deliberate_asserts,
            inc_assert_density=self.incidental_asserts / denom if denom else 0.0,
            del_assert_density=self.deliberate_asserts / denom if denom else 0.0,
        )


@dataclass
class _FolderAggregates:
    """All aggregated metrics for a folder subtree, computed in a single bottom-up pass."""
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
    path: str  # e.g. "src/payments/billing", "" for the virtual root
    subfolders: dict[str, FolderNode] = field(default_factory=dict)
    files: list[FileSummary] = field(default_factory=list)
    # Cached result of compute_aggregates(); None until first call.
    _agg: _FolderAggregates | None = field(default=None, init=False, repr=False, compare=False)

    def compute_aggregates(self) -> _FolderAggregates:
        """Return aggregated metrics for this subtree, computing once and caching.

        A single bottom-up pass collects all 10 metrics simultaneously, reducing
        index-page rendering from O(n·d·k) to O(n) compared to 9 separate
        recursive traversals.
        """
        if self._agg is not None:
            return self._agg
        agg = _FolderAggregates()
        for f in self.files:
            agg.total_stmts += f.total_stmts
            agg.total_covered += f.total_covered
            agg.arcs_total += f.arcs_total
            agg.arcs_covered += f.arcs_covered
            agg.arcs_deliberate += f.arcs_deliberate
            agg.arcs_incidental += f.arcs_incidental
            agg.deliberate += f.deliberate_covered
            agg.incidental += f.incidental_covered
            agg.incidental_asserts += f.incidental_asserts
            agg.deliberate_asserts += f.deliberate_asserts
        for sub in self.subfolders.values():
            sub_agg = sub.compute_aggregates()
            agg.total_stmts += sub_agg.total_stmts
            agg.total_covered += sub_agg.total_covered
            agg.arcs_total += sub_agg.arcs_total
            agg.arcs_covered += sub_agg.arcs_covered
            agg.arcs_deliberate += sub_agg.arcs_deliberate
            agg.arcs_incidental += sub_agg.arcs_incidental
            agg.deliberate += sub_agg.deliberate
            agg.incidental += sub_agg.incidental
            agg.incidental_asserts += sub_agg.incidental_asserts
            agg.deliberate_asserts += sub_agg.deliberate_asserts
        self._agg = agg
        return agg

    def to_index_row(self) -> IndexRowData:
        agg = self.compute_aggregates()
        denom = agg.total_stmts + agg.arcs_total
        return IndexRowData(
            total_stmts=denom,
            total_pct=self._pct(agg.total_covered + agg.arcs_covered, denom),
            deliberate_pct=self._pct(agg.deliberate + agg.arcs_deliberate, denom),
            incidental_pct=self._pct(agg.incidental + agg.arcs_incidental, denom),
            deliberate_covered=agg.deliberate,
            incidental_covered=agg.incidental,
            incidental_asserts=agg.incidental_asserts,
            deliberate_asserts=agg.deliberate_asserts,
            inc_assert_density=agg.incidental_asserts / denom if denom else 0.0,
            del_assert_density=agg.deliberate_asserts / denom if denom else 0.0,
        )

    @staticmethod
    def _pct(numerator: int, denominator: int) -> float:
        """Coverage percentage; returns 100.0 when denominator is 0 (nothing to cover)."""
        return numerator / denominator * 100.0 if denominator else 100.0


@dataclass
class FileReport:
    summary: FileSummary
    lines: list[LineReport]   # ALL lines in the source file, not just executed ones


@dataclass
class CoverageReport:
    files: list[FileReport]
    root: FolderNode
