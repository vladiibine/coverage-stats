from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pytest

from coverage_stats.executable_lines import ExecutableLinesAnalyzer, FileAnalysis
from coverage_stats.reporters.branch_analysis import BranchWalker
from coverage_stats.reporters.models import (
    _BranchAnalysis,
    CoverageReport,
    FileSummary,
    FileReport,
    FolderNode,
    LineReport,
)
from coverage_stats.store import LineData, SessionStore


class ReportBuilder(Protocol):
    """Protocol for building a CoverageReport from raw session data.

    Implement this to customise any part of the report-building pipeline.
    The default implementation is DefaultReportBuilder.

    Subclassing DefaultReportBuilder and overriding individual methods is
    the recommended way to make targeted changes:

    - Override ``build_folder_tree`` to change how files are grouped.
    - Override ``_analyze_branches`` to change branch-coverage logic.
    - Implement this protocol from scratch for a full replacement.
    """

    def build(self, store: SessionStore, config: pytest.Config) -> CoverageReport: ...


class DefaultReportBuilder:
    """Default implementation of the ReportBuilder protocol."""

    def __init__(
        self,
        analyzer: ExecutableLinesAnalyzer | None = None,
        branch_walker: BranchWalker | None = None,
    ) -> None:
        self._analyzer = analyzer if analyzer is not None else ExecutableLinesAnalyzer()
        self._branch_walker = branch_walker if branch_walker is not None else BranchWalker()

    def build(self, store: SessionStore, config: pytest.Config) -> CoverageReport:
        """Build a CoverageReport from the session store and pytest config."""
        file_reports: list[FileReport] = []
        for abs_path, line_data in store.files().items():
            try:
                rel_path = Path(abs_path).relative_to(config.rootpath).as_posix()
            except ValueError:
                rel_path = Path(abs_path).as_posix()

            file_analysis = self._analyzer.analyze(abs_path)
            if file_analysis is not None:
                source_map = {i + 1: line for i, line in enumerate(file_analysis.source_lines)}
                all_linenos: list[int] = list(range(1, len(file_analysis.source_lines) + 1))
                executable = file_analysis.executable_lines
                excluded = file_analysis.excluded_lines
            else:
                all_linenos = sorted(line_data.keys())
                source_map = {}
                executable = set()
                excluded = set()

            total_stmts = len(executable) if (executable or Path(abs_path).exists()) else len(line_data)

            branch_analysis = self._analyze_branches(file_analysis, line_data, excluded)

            total_covered = sum(
                1 for ln in executable
                if ln in line_data and (line_data[ln].deliberate_executions > 0 or line_data[ln].incidental_executions > 0)
            )
            deliberate_covered = sum(
                1 for ln in executable if ln in line_data and line_data[ln].deliberate_executions > 0
            )
            incidental_covered = sum(
                1 for ln in executable if ln in line_data and line_data[ln].incidental_executions > 0
            )
            incidental_asserts = sum(ld.incidental_asserts for ld in line_data.values())
            deliberate_asserts = sum(ld.deliberate_asserts for ld in line_data.values())
            incidental_test_ids = frozenset().union(*(ld.incidental_test_ids for ld in line_data.values()))
            deliberate_test_ids = frozenset().union(*(ld.deliberate_test_ids for ld in line_data.values()))

            total_denom = total_stmts + branch_analysis.arcs_total
            total_pct = self._pct(total_covered + branch_analysis.arcs_covered, total_denom)
            deliberate_pct = self._pct(deliberate_covered + branch_analysis.arcs_deliberate, total_denom)
            incidental_pct = self._pct(incidental_covered + branch_analysis.arcs_incidental, total_denom)

            partial_count = len(branch_analysis.partial & executable)

            summary = FileSummary(
                rel_path=rel_path,
                abs_path=abs_path,
                total_stmts=total_stmts,
                total_covered=total_covered,
                deliberate_covered=deliberate_covered,
                incidental_covered=incidental_covered,
                arcs_total=branch_analysis.arcs_total,
                arcs_covered=branch_analysis.arcs_covered,
                arcs_deliberate=branch_analysis.arcs_deliberate,
                arcs_incidental=branch_analysis.arcs_incidental,
                total_pct=total_pct,
                deliberate_pct=deliberate_pct,
                incidental_pct=incidental_pct,
                partial_count=partial_count,
                incidental_asserts=incidental_asserts,
                deliberate_asserts=deliberate_asserts,
                incidental_test_ids=incidental_test_ids,
                deliberate_test_ids=deliberate_test_ids,
            )

            line_reports: list[LineReport] = []
            for lineno in all_linenos:
                line_entry: LineData | None = line_data.get(lineno)
                source_text = source_map.get(lineno, "")
                line_reports.append(LineReport(
                    lineno=lineno,
                    source_text=source_text,
                    executable=lineno in executable,
                    partial=lineno in branch_analysis.partial,
                    excluded=lineno in excluded,
                    incidental_executions=line_entry.incidental_executions if line_entry else 0,
                    deliberate_executions=line_entry.deliberate_executions if line_entry else 0,
                    incidental_asserts=line_entry.incidental_asserts if line_entry else 0,
                    deliberate_asserts=line_entry.deliberate_asserts if line_entry else 0,
                    incidental_tests=line_entry.incidental_tests if line_entry else 0,
                    deliberate_tests=line_entry.deliberate_tests if line_entry else 0,
                    incidental_test_ids=frozenset(line_entry.incidental_test_ids) if line_entry else frozenset(),
                    deliberate_test_ids=frozenset(line_entry.deliberate_test_ids) if line_entry else frozenset(),
                ))

            file_reports.append(FileReport(summary=summary, lines=line_reports))

        root = self.build_folder_tree([fr.summary for fr in file_reports])
        return CoverageReport(files=file_reports, root=root)

    def build_folder_tree(self, summaries: list[FileSummary]) -> FolderNode:
        """Group a flat list of FileSummary objects into a folder tree."""
        root = FolderNode(path="")
        for s in summaries:
            parts = s.rel_path.split("/")
            node = root
            for part in parts[:-1]:
                if part not in node.subfolders:
                    parent_path = f"{node.path}/{part}" if node.path else part
                    node.subfolders[part] = FolderNode(path=parent_path)
                node = node.subfolders[part]
            node.files.append(s)
        return root

    def _analyze_branches(self, file_analysis: FileAnalysis | None, lines: dict[int, LineData], excluded: set[int] | None = None) -> _BranchAnalysis:
        """Analyze branch coverage, returning partial line numbers and arc counts.

        Arc counting mirrors coverage.py's branch-inclusive formula so that:
            (stmts_covered + arcs_covered) / (stmts_total + arcs_total)
        matches coverage.py's "Cover %" when run with --cov-branch.

        Arc rules:
        - if/while/for: 2 arcs each (true branch, false branch); unreached still
          contributes to arcs_total but 0 to arcs_covered.
        - match non-last case: 2 arcs (body taken, next case reached).
        - match last wildcard case: 0 arcs (always matches — no branching).
        - match last non-wildcard case: 1 arc (body taken).

        *file_analysis* is ``None`` when the source file could not be read or
        parsed, in which case an empty ``_BranchAnalysis`` is returned.
        """
        if file_analysis is None:
            return _BranchAnalysis(partial=set(), arcs_total=0, arcs_covered=0, arcs_deliberate=0, arcs_incidental=0)

        _excluded = excluded or set()
        partial: set[int] = set()
        arcs_covered = 0
        arcs_deliberate = 0
        arcs_incidental = 0

        if file_analysis.static_arcs is not None:
            # Use coverage.py's arc data for the denominator — this matches
            # coverage.py's branch-coverage denominator exactly regardless of
            # Python version or compiler optimisations.
            arcs_total = len(file_analysis.static_arcs)
            # Source lines whose "exit" (negative-target) arc is in static_arcs.
            # BranchWalker returns false_target=None when the false branch exits
            # the current scope; we match those to coverage.py's negative arcs.
            exit_sources = {src for src, tgt in file_analysis.static_arcs if tgt < 0}

            for bd in self._branch_walker.walk_branches(file_analysis.tree, lines):
                if bd.node_line in _excluded:
                    continue
                # Only count arcs that coverage.py also counts.  This filters
                # out while-True headers and any other construct the static arc
                # set doesn't include.
                true_in_static = (bd.node_line, bd.true_target) in file_analysis.static_arcs
                # BranchWalker uses a positive sibling line for the false target
                # when one exists, and None when the false branch exits the scope.
                # The latter corresponds to a negative arc in static_arcs.
                false_in_static = (
                    bd.false_target is not None
                    and (bd.node_line, bd.false_target) in file_analysis.static_arcs
                ) or (
                    bd.false_target is None
                    and bd.node_line in exit_sources
                )
                if not true_in_static and not false_in_static:
                    continue

                if true_in_static:
                    arcs_covered += (1 if bd.true_taken else 0)
                    arcs_deliberate += (1 if bd.deliberate_true else 0)
                    arcs_incidental += (1 if bd.incidental_true else 0)
                if false_in_static:
                    arcs_covered += (1 if bd.false_taken else 0)
                    arcs_deliberate += (1 if bd.deliberate_false else 0)
                    arcs_incidental += (1 if bd.incidental_false else 0)

                # bd.is_partial already encodes "was reached and not fully covered"
                # correctly for every node type (if/for/while and match cases).
                # We only add to partial when at least one arc for this node is
                # tracked by the static arc set.
                if bd.is_partial and (true_in_static or false_in_static):
                    partial.add(bd.node_line)
        else:
            # Fallback when coverage.py is not available: use BranchWalker's
            # own arc counting.
            arcs_total = 0
            for bd in self._branch_walker.walk_branches(file_analysis.tree, lines):
                if bd.node_line in _excluded:
                    continue

                # Arcs whose target is an excluded line don't count.
                # A branch with only one non-excluded target is not a real
                # decision point — skip it entirely (mirrors coverage.py's
                # behaviour of counting 0 arcs for such branches).
                true_excluded = bd.true_target in _excluded
                false_excluded = bd.false_target is not None and bd.false_target in _excluded
                effective_arc_count = bd.arc_count - (1 if true_excluded else 0) - (1 if false_excluded else 0)
                if effective_arc_count < 2:
                    continue

                arcs_total += effective_arc_count
                if not true_excluded:
                    arcs_covered += (1 if bd.true_taken else 0)
                    arcs_deliberate += (1 if bd.deliberate_true else 0)
                    arcs_incidental += (1 if bd.incidental_true else 0)
                if not false_excluded:
                    arcs_covered += (1 if bd.false_taken else 0)
                    arcs_deliberate += (1 if bd.deliberate_false else 0)
                    arcs_incidental += (1 if bd.incidental_false else 0)

                # Recompute is_partial considering only non-excluded arcs.
                if bd.is_partial:
                    if false_excluded:
                        is_partial = not bd.true_taken
                    elif true_excluded:
                        is_partial = not bd.false_taken
                    else:
                        is_partial = True
                else:
                    is_partial = False

                if is_partial:
                    partial.add(bd.node_line)

        return _BranchAnalysis(
            partial=partial,
            arcs_total=arcs_total,
            arcs_covered=arcs_covered,
            arcs_deliberate=arcs_deliberate,
            arcs_incidental=arcs_incidental,
        )

    @staticmethod
    def _pct(numerator: int, denominator: int) -> float:
        """Coverage percentage; returns 100.0 when denominator is 0 (nothing to cover)."""
        return numerator / denominator * 100.0 if denominator else 100.0