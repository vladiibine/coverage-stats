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
            else:
                all_linenos = sorted(line_data.keys())
                source_map = {}
                executable = set()

            total_stmts = len(executable) if (executable or Path(abs_path).exists()) else len(line_data)

            branch_analysis = self._analyze_branches(file_analysis, line_data)

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
                    incidental_executions=line_entry.incidental_executions if line_entry else 0,
                    deliberate_executions=line_entry.deliberate_executions if line_entry else 0,
                    incidental_asserts=line_entry.incidental_asserts if line_entry else 0,
                    deliberate_asserts=line_entry.deliberate_asserts if line_entry else 0,
                    incidental_tests=line_entry.incidental_tests if line_entry else 0,
                    deliberate_tests=line_entry.deliberate_tests if line_entry else 0,
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

    def _analyze_branches(self, file_analysis: FileAnalysis | None, lines: dict[int, LineData]) -> _BranchAnalysis:
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

        partial: set[int] = set()
        arcs_total = 0
        arcs_covered = 0
        arcs_deliberate = 0
        arcs_incidental = 0

        for bd in self._branch_walker.walk_branches(file_analysis.tree, lines):
            arcs_total += bd.arc_count
            arcs_covered += (1 if bd.true_taken else 0) + (1 if bd.false_taken else 0)
            arcs_deliberate += (1 if bd.deliberate_true else 0) + (1 if bd.deliberate_false else 0)
            arcs_incidental += (1 if bd.incidental_true else 0) + (1 if bd.incidental_false else 0)
            if bd.is_partial:
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