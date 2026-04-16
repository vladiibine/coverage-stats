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
from coverage_stats.store import ArcData, LineData, SessionStore


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

            branch_analysis = self._analyze_branches(file_analysis, line_data, excluded, store=store, abs_path=abs_path)

            # Build statement span map for multi-line statement consolidation.
            # If any line within a multi-line statement's span was executed,
            # the statement (its start line) is considered covered.  This fixes
            # the tracing gap where Python's tracer doesn't fire line events
            # for every line of a multi-line statement (e.g. `return (\n  ...)`).
            stmt_spans = self._build_stmt_spans(file_analysis) if file_analysis is not None else {}

            total_covered = sum(
                1 for ln in executable
                if self._is_stmt_covered(ln, line_data, stmt_spans)
            )
            deliberate_covered = sum(
                1 for ln in executable
                if self._is_stmt_covered(ln, line_data, stmt_spans, deliberate=True)
            )
            incidental_covered = sum(
                1 for ln in executable
                if self._is_stmt_covered(ln, line_data, stmt_spans, incidental=True)
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

    def _analyze_branches(
        self,
        file_analysis: FileAnalysis | None,
        lines: dict[int, LineData],
        excluded: set[int] | None = None,
        *,
        store: SessionStore | None = None,
        abs_path: str | None = None,
    ) -> _BranchAnalysis:
        """Analyze branch coverage, returning partial line numbers and arc counts.

        When observed arc data is available (from the tracer) and static_arcs
        are present (from coverage.py's PythonParser), branch coverage is
        computed by direct arc lookup — no heuristics needed.

        Falls back to BranchWalker heuristics when arc data is unavailable
        (e.g. old serialized stores without arc data, or when coverage.py is
        not installed).

        *file_analysis* is ``None`` when the source file could not be read or
        parsed, in which case an empty ``_BranchAnalysis`` is returned.
        """
        if file_analysis is None:
            return _BranchAnalysis(partial=set(), arcs_total=0, arcs_covered=0, arcs_deliberate=0, arcs_incidental=0)

        _excluded = excluded or set()

        # Try the direct arc-lookup path: requires both static_arcs and
        # observed arc data from the tracer.  Only use when the store
        # actually contains arc data (i.e. was populated by an arc-aware
        # tracer, not an older store without arc recording).
        observed_arcs: dict[tuple[int, int], ArcData] | None = None
        if store is not None and abs_path is not None and store.has_arc_data():
            observed_arcs = store.arcs_for_file(abs_path)

        if file_analysis.static_arcs is not None and observed_arcs is not None:
            return self._analyze_branches_from_arcs(
                file_analysis.static_arcs, observed_arcs, _excluded,
                multiline_map=file_analysis.multiline_map,
            )

        # Fallback: heuristic-based branch detection via BranchWalker.
        return self._analyze_branches_heuristic(file_analysis, lines, _excluded)

    def _analyze_branches_from_arcs(
        self,
        static_arcs: set[tuple[int, int]],
        observed_arcs: dict[tuple[int, int], ArcData],
        excluded: set[int],
        multiline_map: dict[int, int] | None = None,
    ) -> _BranchAnalysis:
        """Compute branch coverage by directly looking up observed arcs against static_arcs.

        This eliminates all heuristic-based branch detection.  Each arc in
        static_arcs is checked against the observed arc dict from the tracer.

        multiline_map normalises observed arc targets: coverage.py's PythonParser
        maps every physical line inside a multi-line statement to the statement's
        first line (e.g. lines 320-324 of a ternary expression all map to 320).
        The tracer fires LINE events at the raw bytecode-level line, so an arc like
        (318, 322) must be normalised to (318, 320) before matching static_arcs.
        """
        arcs_total = len(static_arcs)
        arcs_covered = 0
        arcs_deliberate = 0
        arcs_incidental = 0
        partial: set[int] = set()

        # Group arcs by source line for partial detection
        from collections import defaultdict
        arcs_by_source: defaultdict[int, list[bool]] = defaultdict(list)

        # Build a normalised view of observed_arcs: map each (src, raw_tgt) to
        # (src, normalised_tgt) using multiline_map so that tracer arcs that land
        # mid-expression (e.g. (318, 322)) match PythonParser's static arcs
        # (e.g. (318, 320)) which always use the first line of the expression.
        if multiline_map:
            normalised_observed: dict[tuple[int, int], ArcData] = {}
            for (src, tgt), ad in observed_arcs.items():
                key = (src, multiline_map.get(tgt, tgt))
                if key not in normalised_observed:
                    normalised_observed[key] = ad
            lookup = normalised_observed
        else:
            lookup = observed_arcs

        for src, tgt in static_arcs:
            arc_data = lookup.get((src, tgt))
            taken = arc_data is not None and (arc_data.incidental_executions + arc_data.deliberate_executions) > 0
            arcs_by_source[src].append(taken)
            if taken:
                assert arc_data is not None
                arcs_covered += 1
                if arc_data.deliberate_executions > 0:
                    arcs_deliberate += 1
                if arc_data.incidental_executions > 0:
                    arcs_incidental += 1

        # Partial: source lines where some arcs were taken but not all
        for src, taken_list in arcs_by_source.items():
            if any(taken_list) and not all(taken_list):
                partial.add(src)

        return _BranchAnalysis(
            partial=partial,
            arcs_total=arcs_total,
            arcs_covered=arcs_covered,
            arcs_deliberate=arcs_deliberate,
            arcs_incidental=arcs_incidental,
        )

    def _analyze_branches_heuristic(
        self,
        file_analysis: FileAnalysis,
        lines: dict[int, LineData],
        excluded: set[int],
    ) -> _BranchAnalysis:
        """Fallback branch analysis using BranchWalker heuristics.

        Used when observed arc data is not available (e.g. old serialized
        stores, or when coverage.py is not installed).
        """
        partial: set[int] = set()
        arcs_covered = 0
        arcs_deliberate = 0
        arcs_incidental = 0

        if file_analysis.static_arcs is not None:
            arcs_total = len(file_analysis.static_arcs)
            exit_sources = {src for src, tgt in file_analysis.static_arcs if tgt < 0}

            for bd in self._branch_walker.walk_branches(file_analysis.tree, lines):
                if bd.node_line in excluded:
                    continue
                true_in_static = (bd.node_line, bd.true_target) in file_analysis.static_arcs
                if bd.false_target is not None:
                    false_in_static = (bd.node_line, bd.false_target) in file_analysis.static_arcs
                    if not false_in_static and bd.node_line in exit_sources:
                        false_in_static = True
                elif bd.node_line in exit_sources:
                    false_in_static = True
                else:
                    false_in_static = any(
                        s == bd.node_line and (s, t) != (bd.node_line, bd.true_target)
                        for s, t in file_analysis.static_arcs
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

                if bd.is_partial and (true_in_static or false_in_static):
                    partial.add(bd.node_line)
        else:
            arcs_total = 0
            for bd in self._branch_walker.walk_branches(file_analysis.tree, lines):
                if bd.node_line in excluded:
                    continue

                true_excluded = bd.true_target in excluded
                false_excluded = bd.false_target is not None and bd.false_target in excluded
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
    def _build_stmt_spans(file_analysis: FileAnalysis) -> dict[int, list[int]]:
        """Build a map from executable statement start lines to all lines in their span.

        For each AST statement node whose start line is executable, records all
        line numbers from ``node.lineno`` to ``node.end_lineno`` (inclusive).
        Only includes statements that span multiple lines — single-line
        statements don't need consolidation.
        """
        import ast
        spans: dict[int, list[int]] = {}
        executable = file_analysis.executable_lines
        for node in ast.walk(file_analysis.tree):
            if not isinstance(node, ast.stmt):
                continue
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            if start not in executable or end is None or end <= start:
                continue
            spans[start] = list(range(start, end + 1))
        return spans

    @staticmethod
    def _is_stmt_covered(
        ln: int,
        line_data: dict[int, LineData],
        stmt_spans: dict[int, list[int]],
        *,
        deliberate: bool = False,
        incidental: bool = False,
    ) -> bool:
        """Check if an executable statement is covered, considering multi-line spans.

        If the statement spans multiple lines, it is covered when any line in
        its span has execution data.  This fixes the tracing gap where Python
        doesn't fire line events for every line of a multi-line statement.
        """
        def _has_execution(ld: LineData | None) -> bool:
            if ld is None:
                return False
            if deliberate:
                return ld.deliberate_executions > 0
            if incidental:
                return ld.incidental_executions > 0
            return ld.deliberate_executions > 0 or ld.incidental_executions > 0

        # Fast path: check the start line directly
        if _has_execution(line_data.get(ln)):
            return True
        # Multi-line consolidation: check all lines in the statement's span
        span = stmt_spans.get(ln)
        if span is not None:
            return any(_has_execution(line_data.get(sl)) for sl in span)
        return False

    @staticmethod
    def _pct(numerator: int, denominator: int) -> float:
        """Coverage percentage; returns 100.0 when denominator is 0 (nothing to cover)."""
        return numerator / denominator * 100.0 if denominator else 100.0