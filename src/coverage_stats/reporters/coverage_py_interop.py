from __future__ import annotations

import ast
import sys
import warnings
from typing import Any, Callable, Protocol

from coverage_stats.reporters.models import _is_wildcard_case
from coverage_stats.store import LineData, SessionStore


class CoveragePyInteropProto(Protocol):
    """Protocol for coverage.py data injection.

    The default implementation is ``CoveragePyInterop``.
    """

    def patch_coverage_save(
        self, store: SessionStore, flush_pre_test_lines: Callable[[], None],
    ) -> None: ...

    def inject_into_coverage_py(self, store: SessionStore) -> None: ...


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

    _COVERAGE_MIN_VERSION = (7, 0)

    def _check_coverage_version(self) -> bool:
        """Return True if coverage.py is installed and meets the minimum supported version.

        Emits a warning and returns False when coverage.py is too old, so callers
        can skip injection rather than hitting confusing AttributeErrors.
        """
        try:
            import coverage
            parts = coverage.__version__.split(".")[:2]
            ver = tuple(int(x) for x in parts if x.isdigit())
            if ver < self._COVERAGE_MIN_VERSION:
                warnings.warn(
                    f"coverage-stats: coverage.py {coverage.__version__} is below the "
                    f"minimum supported version {'.'.join(map(str, self._COVERAGE_MIN_VERSION))}; "
                    "interop disabled"
                )
                return False
            return True
        except ImportError:
            return False

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
                    if is_last and self._is_wildcard_case(case):
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
        return {path: self.compute_full_arcs(path, line_data) for path, line_data in store.files().items()}

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
        if not self._check_coverage_version():
            return
        try:
            import coverage as coverage_module
        except ImportError:
            return
        if not hasattr(coverage_module.Coverage, "current"):
            warnings.warn("coverage-stats: coverage.py API changed (Coverage.current missing) — interop skipped")
            return
        cov = coverage_module.Coverage.current()
        if cov is None:
            return
        if not hasattr(cov, "get_data") or not hasattr(cov, "save"):
            warnings.warn("coverage-stats: coverage.py API changed (Coverage.get_data/save missing) — interop skipped")
            return
        interop = self
        _orig_save = cov.save

        def _save_with_injection(*args: Any, **kwargs: Any) -> object:
            cov.save = _orig_save  # type: ignore[method-assign]  # un-patch first (avoid recursion)
            try:
                flush_pre_test_lines()
                data = cov.get_data()
                if not hasattr(data, "has_arcs") or not hasattr(data, "add_lines") or not hasattr(data, "add_arcs"):
                    warnings.warn("coverage-stats: coverage.py CoverageData API changed — interop skipped")
                elif data.has_arcs():
                    arcs = interop.full_arcs_for_store(store)
                    if arcs:
                        data.add_arcs(arcs)
                else:
                    data.add_lines(store.lines_by_file())
            except Exception as exc:
                warnings.warn(f"coverage-stats: coverage.py interop failed (version mismatch?): {exc}")
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
        if not self._check_coverage_version():
            return
        try:
            import coverage as coverage_module
        except ImportError:
            return
        if not hasattr(coverage_module.Coverage, "current"):
            warnings.warn("coverage-stats: coverage.py API changed (Coverage.current missing) — interop skipped")
            return
        cov = coverage_module.Coverage.current()
        if cov is None:
            return
        if not hasattr(cov, "get_data"):
            warnings.warn("coverage-stats: coverage.py API changed (Coverage.get_data missing) — interop skipped")
            return
        try:
            data = cov.get_data()
            if not hasattr(data, "has_arcs") or not hasattr(data, "add_lines") or not hasattr(data, "add_arcs"):
                warnings.warn("coverage-stats: coverage.py CoverageData API changed — interop skipped")
                return
            if data.has_arcs():
                arcs = self.full_arcs_for_store(store)
                if arcs:
                    data.add_arcs(arcs)
            else:
                data.add_lines(store.lines_by_file())
        except Exception as exc:
            warnings.warn(f"coverage-stats: coverage.py interop failed (version mismatch?): {exc}")

    @staticmethod
    def _is_wildcard_case(case: ast.match_case) -> bool:
        return _is_wildcard_case(case)