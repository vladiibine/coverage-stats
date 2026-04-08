from __future__ import annotations

import ast
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import pytest

from coverage_stats.executable_lines import get_executable_lines
from coverage_stats.store import LineData, SessionStore


def _pct(numerator: int, denominator: int) -> float:
    """Coverage percentage; returns 100.0 when denominator is 0 (nothing to cover)."""
    return numerator / denominator * 100.0 if denominator else 100.0


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
            total_pct=_pct(agg.total_covered + agg.arcs_covered, denom),
            deliberate_pct=_pct(agg.deliberate + agg.arcs_deliberate, denom),
            incidental_pct=_pct(agg.incidental + agg.arcs_incidental, denom),
            deliberate_covered=agg.deliberate,
            incidental_covered=agg.incidental,
            incidental_asserts=agg.incidental_asserts,
            deliberate_asserts=agg.deliberate_asserts,
            inc_assert_density=agg.incidental_asserts / denom if denom else 0.0,
            del_assert_density=agg.deliberate_asserts / denom if denom else 0.0,
        )


@dataclass
class FileReport:
    summary: FileSummary
    lines: list[LineReport]   # ALL lines in the source file, not just executed ones


@dataclass
class CoverageReport:
    files: list[FileReport]
    root: FolderNode


def _is_wildcard_case(case: ast.match_case) -> bool:
    """Mirror coverage.py's wildcard detection logic for match-case statements."""
    pattern = case.pattern
    while isinstance(pattern, ast.MatchOr):
        pattern = pattern.patterns[-1]
    while isinstance(pattern, ast.MatchAs) and pattern.pattern is not None:
        pattern = pattern.pattern
    return isinstance(pattern, ast.MatchAs) and pattern.pattern is None and case.guard is None


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


class CoveragePyInteropProto(Protocol):
    """Protocol for coverage.py data injection.

    The default implementation is ``CoveragePyInterop``.
    """

    def patch_coverage_save(
        self, store: SessionStore, flush_pre_test_lines: Callable[[], None],
    ) -> None: ...

    def inject_into_coverage_py(self, store: SessionStore) -> None: ...


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


class CoveragePyInterop:
    """Computes arc data suitable for injection into coverage.py's CoverageData.

    On Python < 3.12, coverage-stats displaces coverage.py's C tracer via
    sys.settrace, so coverage.py records nothing during tests.  This class
    reconstructs the arc (and optionally line) data from coverage-stats'
    SessionStore so it can be injected before coverage.py writes to disk.

    Two levels of arc detail:

    - ``compute_arcs``: branch arcs only (if/for/while/match).
    - ``compute_full_arcs``: branch arcs + sequential + entry/exit arcs for
      every executed scope, producing the complete set coverage.py needs to
      derive line coverage when in arc (--cov-branch) mode.
    """

    def compute_arcs(self, path: str, lines: dict[int, LineData]) -> list[tuple[int, int]]:
        """Compute the (from_line, to_line) arc pairs that were actually traversed.

        Returns a list suitable for passing to coverage.CoverageData.add_arcs().
        Uses execution-count heuristics to infer which branches were taken, then
        maps them to concrete line pairs.

        For false branches without an explicit else/elif, the destination is the
        first statement that follows the entire if/while/for block in source order.
        This is found by walking up the AST parent chain until a next sibling
        statement is found.  Arcs whose destination cannot be determined (e.g. a
        branch at the very end of a module with nothing following it) are omitted
        rather than guessed.
        """
        def _count(lineno: int) -> int:
            ld = lines.get(lineno)
            return (ld.incidental_executions + ld.deliberate_executions) if ld else 0

        try:
            source = open(path, encoding="utf-8", errors="replace").read()
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            return []

        # Map id(node) → parent so we can walk up the tree.
        parent_map: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent_map[id(child)] = node

        def _next_sibling_lineno(node: ast.AST) -> int | None:
            """Return the lineno of the first statement after *node*.

            Searches each statement-body attribute of the parent in turn.  If
            *node* is the last statement in its parent body, recurse up to find
            the continuation after the enclosing block.  Returns None when there
            is no continuation (e.g. end of module).
            """
            parent = parent_map.get(id(node))
            if parent is None:
                return None
            for attr in ("body", "orelse", "handlers", "finalbody"):
                siblings: list[ast.AST] = getattr(parent, attr, None) or []
                try:
                    idx = siblings.index(node)
                except ValueError:
                    continue
                if idx + 1 < len(siblings):
                    return int(siblings[idx + 1].lineno)  # type: ignore[attr-defined]
                # node is last in this list — look for a continuation higher up
                return _next_sibling_lineno(parent)
            return None

        arcs: list[tuple[int, int]] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.If, ast.While, ast.For)):
                continue
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
                    arcs.append((node.lineno, body_lineno))
                if false_taken:
                    arcs.append((node.lineno, orelse_lineno))
            else:
                false_taken = if_count > body_count
                if true_taken:
                    arcs.append((node.lineno, body_lineno))
                if false_taken:
                    next_line = _next_sibling_lineno(node)
                    if next_line is not None:
                        arcs.append((node.lineno, next_line))

        if sys.version_info >= (3, 10):
            for node in ast.walk(tree):
                if not isinstance(node, ast.Match):
                    continue
                for i, case in enumerate(node.cases):
                    case_line = case.pattern.lineno
                    is_last = i == len(node.cases) - 1
                    if is_last and _is_wildcard_case(case):
                        continue
                    body_lineno = case.body[0].lineno
                    body_taken = _count(body_lineno) > 0
                    if is_last:
                        if body_taken:
                            arcs.append((case_line, body_lineno))
                    else:
                        next_case_lineno = node.cases[i + 1].pattern.lineno
                        next_case_taken = _count(next_case_lineno) > 0
                        if body_taken:
                            arcs.append((case_line, body_lineno))
                        if next_case_taken:
                            arcs.append((case_line, next_case_lineno))

        return arcs

    def compute_full_arcs(self, path: str, lines: dict[int, LineData]) -> list[tuple[int, int]]:
        """Compute comprehensive execution arcs for coverage.py branch-mode injection.

        When coverage.py runs with --cov-branch, it stores arc data and derives
        line coverage from arcs.  add_lines() is rejected in that mode, so we
        must provide ALL coverage information via add_arcs().

        This generates three kinds of arcs:
        1. Function/module entry and exit arcs (negative line numbers)
        2. Sequential arcs between consecutive executed lines in the same scope
        3. Branch arcs from compute_arcs() (if/for/while/match)

        Coverage.py ignores injected arcs that fall outside its own
        arc_possibilities set, so slightly imprecise sequential arcs (e.g.
        across a return boundary) are harmless for branch analysis while still
        ensuring every executed line appears in the arc data for line coverage.
        """
        def _count(lineno: int) -> int:
            ld = lines.get(lineno)
            return (ld.incidental_executions + ld.deliberate_executions) if ld else 0

        executed = sorted(ln for ln in lines if _count(ln) > 0)
        if not executed:
            return []

        try:
            source = open(path, encoding="utf-8", errors="replace").read()
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            return []

        # Collect function definitions with their line ranges.
        func_defs: list[tuple[int, int]] = []  # (def_line, end_line)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = node.end_lineno if node.end_lineno is not None else node.lineno
                func_defs.append((node.lineno, end))

        def _get_scope(lineno: int) -> int | None:
            """Return def_line of the innermost enclosing function, or None for module-level."""
            best: int | None = None
            best_size = float("inf")
            for def_line, end_line in func_defs:
                if def_line < lineno <= end_line:
                    size = end_line - def_line
                    if size < best_size:
                        best_size = size
                        best = def_line
            return best

        # Group executed lines by scope.
        scopes: dict[int | None, list[int]] = {}
        for ln in executed:
            scope = _get_scope(ln)
            scopes.setdefault(scope, []).append(ln)

        arcs: set[tuple[int, int]] = set()

        # Module-level arcs.
        module_lines = scopes.get(None, [])
        if module_lines:
            scope_id = module_lines[0]
            arcs.add((-scope_id, module_lines[0]))
            for i in range(len(module_lines) - 1):
                arcs.add((module_lines[i], module_lines[i + 1]))
            arcs.add((module_lines[-1], -scope_id))

        # Function-level arcs.
        for scope_key, fn_lines in scopes.items():
            if scope_key is None:
                continue
            arcs.add((-scope_key, fn_lines[0]))
            for i in range(len(fn_lines) - 1):
                arcs.add((fn_lines[i], fn_lines[i + 1]))
            arcs.add((fn_lines[-1], -scope_key))

        # Branch arcs (may duplicate sequential arcs — set handles dedup).
        for arc in self.compute_arcs(path, lines):
            arcs.add(arc)

        return list(arcs)

    def full_arcs_for_store(self, store: SessionStore) -> dict[str, list[tuple[int, int]]]:
        """Compute comprehensive execution arcs for every file in *store*.

        Returns the full set of arcs (entry/exit + sequential + branch) needed
        when coverage.py is in branch mode and add_lines() cannot be used.
        """
        files: dict[str, dict[int, LineData]] = {}
        for (path, lineno), ld in store._data.items():
            files.setdefault(path, {})[lineno] = ld
        return {path: self.compute_full_arcs(path, line_data) for path, line_data in files.items()}

    def patch_coverage_save(
        self,
        store: SessionStore,
        flush_pre_test_lines: Callable[[], None],
    ) -> None:
        """Patch Coverage.save() to inject our data just before it writes to disk.

        Call this after the tracer is installed but before any tests run.  The
        patch is self-removing: it fires once, injects store data (plus any
        accumulated pre-test lines via *flush_pre_test_lines*), then restores
        the original save() method.

        pytest-cov 7+ calls cov.save() inside a pytest_runtestloop wrapper that
        completes *before* pytest_sessionfinish fires, so a pytest_sessionfinish
        hook arrives too late.  Patching the method itself is hook-ordering
        independent: our data is always present in the CoverageData object at
        the exact moment it is flushed to disk.
        """
        try:
            import coverage as coverage_module
        except ImportError:
            return
        cov = coverage_module.Coverage.current()
        if cov is None:
            return
        interop = self
        _orig_save = cov.save

        def _save_with_injection(*args: Any, **kwargs: Any) -> object:
            cov.save = _orig_save  # type: ignore[method-assign]  # un-patch first (avoid recursion)
            try:
                flush_pre_test_lines()
                data = cov.get_data()
                if data.has_arcs():
                    arcs = interop.full_arcs_for_store(store)
                    if arcs:
                        data.add_arcs(arcs)
                else:
                    data.add_lines(store.lines_by_file())
            except Exception as exc:
                warnings.warn(f"coverage-stats: failed to inject data into coverage.py (1): {exc}")
            return _orig_save(*args, **kwargs)

        cov.save = _save_with_injection  # type: ignore[assignment]

    def inject_into_coverage_py(self, store: SessionStore) -> None:
        """Inject line/arc data directly into coverage.py's live CoverageData.

        Best-effort fallback for coverage tool integrations that call
        cov.save() from pytest_sessionfinish (older pytest-cov versions, custom
        runners, etc.).  The primary injection path is ``patch_coverage_save``,
        which covers pytest-cov 7+ that saves inside a pytest_runtestloop
        wrapper.
        """
        try:
            import coverage as coverage_module
        except ImportError:
            return
        cov = coverage_module.Coverage.current()
        if cov is None:
            return
        try:
            data = cov.get_data()
            if data.has_arcs():
                arcs = self.full_arcs_for_store(store)
                if arcs:
                    data.add_arcs(arcs)
            else:
                data.add_lines(store.lines_by_file())
        except Exception as exc:
            warnings.warn(f"coverage-stats: failed to inject data into coverage.py (2): {exc}")

# TODO - get rid of these shims, as AI could think these kinds of functions should be used in the library's code,
#  outside of tests, which they should not be
# Module-level shims for backward compatibility in tests
def build_report(store: SessionStore, config: pytest.Config) -> CoverageReport:
    return DefaultReportBuilder().build(store, config)


def build_folder_tree(summaries: list[FileSummary]) -> FolderNode:
    return DefaultReportBuilder().build_folder_tree(summaries)


def _analyze_branches(path: str, lines: dict[int, LineData]) -> _BranchAnalysis:
    return DefaultReportBuilder()._analyze_branches(path, lines)

