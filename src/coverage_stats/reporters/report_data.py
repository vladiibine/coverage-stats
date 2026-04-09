from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path
from typing import Protocol

import pytest

from coverage_stats.executable_lines import get_executable_lines
from coverage_stats.reporters.models import (
    _BranchAnalysis,
    _pct,
    _is_wildcard_case,
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

    def build(self, store: SessionStore, config: pytest.Config) -> CoverageReport:
        """Build a CoverageReport from the session store and pytest config."""
        # Group store data by relative path
        files: dict[str, dict[int, LineData]] = defaultdict(dict)
        for (abs_path, lineno), ld in store._data.items():
            try:
                rel = Path(abs_path).relative_to(config.rootpath).as_posix()
            except ValueError:
                rel = Path(abs_path).as_posix()
            files[rel][lineno] = ld

        # Build abs_path map
        abs_path_map: dict[str, str] = {}
        for (abs_path, _lineno) in store._data.keys():
            try:
                rel = Path(abs_path).relative_to(config.rootpath).as_posix()
            except ValueError:
                rel = Path(abs_path).as_posix()
            abs_path_map[rel] = abs_path

        file_reports: list[FileReport] = []
        for rel_path, line_data in files.items():
            abs_path = abs_path_map.get(rel_path, rel_path)

            try:
                source_lines = Path(abs_path).read_text(encoding="utf-8", errors="replace").splitlines()
                source_map = {i + 1: line for i, line in enumerate(source_lines)}
                all_linenos: list[int] = list(range(1, len(source_lines) + 1))
            except Exception:
                all_linenos = sorted(line_data.keys())
                source_map = {}

            executable = get_executable_lines(abs_path)
            total_stmts = len(executable) if (executable or Path(abs_path).exists()) else len(line_data)

            branch_analysis = self._analyze_branches(abs_path, line_data)

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
            total_pct = _pct(total_covered + branch_analysis.arcs_covered, total_denom)
            deliberate_pct = _pct(deliberate_covered + branch_analysis.arcs_deliberate, total_denom)
            incidental_pct = _pct(incidental_covered + branch_analysis.arcs_incidental, total_denom)

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

    def _analyze_branches(self, path: str, lines: dict[int, LineData]) -> _BranchAnalysis:
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
        """
        def _count(lineno: int) -> int:
            ld = lines.get(lineno)
            return (ld.incidental_executions + ld.deliberate_executions) if ld else 0

        def _del_count(lineno: int) -> int:
            ld = lines.get(lineno)
            return ld.deliberate_executions if ld else 0

        def _inc_count(lineno: int) -> int:
            ld = lines.get(lineno)
            return ld.incidental_executions if ld else 0

        try:
            source = open(path, encoding="utf-8", errors="replace").read()
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            return _BranchAnalysis(partial=set(), arcs_total=0, arcs_covered=0, arcs_deliberate=0, arcs_incidental=0)

        partial: set[int] = set()
        arcs_total = 0
        arcs_covered = 0
        arcs_deliberate = 0
        arcs_incidental = 0

        for node in ast.walk(tree):
            if not isinstance(node, (ast.If, ast.While, ast.For)):
                continue
            arcs_total += 2
            if_count = _count(node.lineno)
            if if_count == 0:
                continue
            body_lineno = node.body[0].lineno
            body_count = _count(body_lineno)
            true_taken = body_count > 0
            if node.orelse:
                orelse_lineno = node.orelse[0].lineno
                false_taken = _count(orelse_lineno) > 0
                if true_taken:
                    arcs_deliberate += 1 if _del_count(body_lineno) > 0 else 0
                    arcs_incidental += 1 if _inc_count(body_lineno) > 0 else 0
                if false_taken:
                    arcs_deliberate += 1 if _del_count(orelse_lineno) > 0 else 0
                    arcs_incidental += 1 if _inc_count(orelse_lineno) > 0 else 0
            else:
                false_taken = if_count > body_count
                if true_taken:
                    arcs_deliberate += 1 if _del_count(body_lineno) > 0 else 0
                    arcs_incidental += 1 if _inc_count(body_lineno) > 0 else 0
                if false_taken:
                    arcs_deliberate += 1 if _del_count(node.lineno) > _del_count(body_lineno) else 0
                    arcs_incidental += 1 if _inc_count(node.lineno) > _inc_count(body_lineno) else 0
            arcs_covered += (1 if true_taken else 0) + (1 if false_taken else 0)
            if not true_taken or not false_taken:
                partial.add(node.lineno)

        if sys.version_info >= (3, 10):
            for node in ast.walk(tree):
                if not isinstance(node, ast.Match):
                    continue
                for i, case in enumerate(node.cases):
                    case_line = case.pattern.lineno
                    is_last = i == len(node.cases) - 1
                    if is_last and _is_wildcard_case(case):
                        # Wildcard always matches — no branching arcs
                        continue
                    elif is_last:
                        arcs_total += 1
                        if _count(case_line) > 0:
                            body_lineno = case.body[0].lineno
                            body_taken = _count(body_lineno) > 0
                            arcs_covered += 1 if body_taken else 0
                            if body_taken:
                                arcs_deliberate += 1 if _del_count(body_lineno) > 0 else 0
                                arcs_incidental += 1 if _inc_count(body_lineno) > 0 else 0
                            if not body_taken:
                                partial.add(case_line)
                    else:
                        arcs_total += 2
                        if _count(case_line) > 0:
                            body_lineno = case.body[0].lineno
                            next_case_lineno = node.cases[i + 1].pattern.lineno
                            body_taken = _count(body_lineno) > 0
                            next_case_taken = _count(next_case_lineno) > 0
                            arcs_covered += (1 if body_taken else 0) + (1 if next_case_taken else 0)
                            if body_taken:
                                arcs_deliberate += 1 if _del_count(body_lineno) > 0 else 0
                                arcs_incidental += 1 if _inc_count(body_lineno) > 0 else 0
                            if next_case_taken:
                                arcs_deliberate += 1 if _del_count(next_case_lineno) > 0 else 0
                                arcs_incidental += 1 if _inc_count(next_case_lineno) > 0 else 0
                            if not body_taken or not next_case_taken:
                                partial.add(case_line)

        return _BranchAnalysis(
            partial=partial,
            arcs_total=arcs_total,
            arcs_covered=arcs_covered,
            arcs_deliberate=arcs_deliberate,
            arcs_incidental=arcs_incidental,
        )
