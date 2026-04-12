from __future__ import annotations

import ast
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field

try:
    from coverage.python import PythonParser as _CovPythonParser  # type: ignore[attr-defined]
    from coverage.config import CoverageConfig as _CovConfig

    _cfg = _CovConfig()
    _COV_EXCLUDE_RE: str | None = "(" + ")|(".join(_cfg.exclude_list) + ")"
    del _cfg
    _HAS_COVERAGE_PARSER = True
except (ImportError, AttributeError, TypeError):
    _HAS_COVERAGE_PARSER = False
    _COV_EXCLUDE_RE = None


@dataclass
class FileAnalysis:
    """The result of reading and parsing a single source file once.

    Created by ``ExecutableLinesAnalyzer.analyze`` and consumed by
    ``DefaultReportBuilder`` to avoid re-reading and re-parsing the same
    source file multiple times during a single reporting run.
    """

    path: str
    tree: ast.Module
    source_lines: list[str]
    executable_lines: set[int]
    excluded_lines: set[int] = field(default_factory=set)
    # Branch arc pairs derived from coverage.py's PythonParser when available.
    # Each entry is a (source_line, target_line) pair for a branch where the
    # source has ≥2 non-excluded positive targets — exactly the set coverage.py
    # uses for its branch-coverage denominator.  None when coverage.py is not
    # installed or its arc data could not be obtained.
    static_arcs: set[tuple[int, int]] | None = None


class ExecutableLinesAnalyzer:
    """AST-based executable line analyser.

    Determines which line numbers in a Python source file contain executable
    statements.  The default implementation mirrors coverage.py's approach:
    parse the source, collect ``ast.stmt`` start lines, and exclude docstrings.

    Subclass and override ``get_executable_lines`` or ``_docstring_lines`` to
    change what counts as executable.
    """

    def analyze(self, path: str) -> FileAnalysis | None:
        """Read and parse *path* once, returning a ``FileAnalysis``.

        Returns ``None`` if the file cannot be read or parsed.  The returned
        object holds the AST, split source lines, and pre-computed executable
        line numbers so callers (e.g. ``DefaultReportBuilder.build``) can
        avoid re-reading and re-parsing the same file for branch analysis.
        """
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                source = fh.read()
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            return None
        source_lines = source.splitlines()
        static_arcs: set[tuple[int, int]] | None = None
        if _HAS_COVERAGE_PARSER:
            try:
                executable, excluded, static_arcs = self._parse_with_coverage(source)
            except Exception:
                excluded = self._excluded_lines(tree, source_lines)
                executable = self._compute_executable_from_tree(tree) - excluded
        else:
            excluded = self._excluded_lines(tree, source_lines)
            executable = self._compute_executable_from_tree(tree) - excluded
        return FileAnalysis(
            path=path,
            tree=tree,
            source_lines=source_lines,
            executable_lines=executable,
            excluded_lines=excluded,
            static_arcs=static_arcs,
        )

    def _parse_with_coverage(self, source: str) -> tuple[set[int], set[int], set[tuple[int, int]]]:
        """Parse source using coverage.py's PythonParser for exact statement matching.

        Returns (executable_lines, excluded_lines, static_arcs).
        ``static_arcs`` is the set of (source, target) arc pairs where the
        source line has ≥2 non-excluded positive targets — matching coverage.py's
        branch-coverage denominator exactly.
        """
        from collections import defaultdict

        p = _CovPythonParser(text=source, exclude=_COV_EXCLUDE_RE)
        p.parse_source()
        excl = set(p.excluded)

        arc_map: dict[int, set[int]] = defaultdict(set)
        for a, b in p.arcs():
            if a > 0:
                arc_map[a].add(b)

        # An arc (src, tgt) is "countable" when its source is non-excluded and
        # its target is either a positive non-excluded line OR a negative line
        # (coverage.py's convention for "exit this scope" arcs, e.g. the false
        # branch of a bare `if` at the end of a function).  A source line is a
        # branch point when it has ≥2 countable arcs.  We store all countable
        # (src, tgt) pairs — including negative targets — so the denominator and
        # partial detection both match coverage.py's HTML output exactly.
        static_arcs: set[tuple[int, int]] = set()
        for src_ln, targets in arc_map.items():
            if src_ln in excl:
                continue
            countable = [t for t in targets if t < 0 or (t > 0 and t not in excl)]
            if len(countable) >= 2:
                for t in countable:
                    static_arcs.add((src_ln, t))

        return set(p.statements), excl, static_arcs

    def get_executable_lines(self, path: str) -> set[int]:
        """Return the set of line numbers that contain executable statements in *path*.

        Uses AST-based statement detection (same approach as coverage.py): parses
        the source and collects the start line of every ``ast.stmt`` node.  This
        correctly handles multi-line expressions and comprehensions — a
        ``y = {x: x**2 for x in range(3)}`` spanning five lines contributes only
        one executable line (the assignment), not five.  Docstrings (the first
        string-literal expression in a module/class/function body) are excluded.

        Returns an empty set if the file cannot be read or compiled.
        """
        fa = self.analyze(path)
        return fa.executable_lines if fa is not None else set()

    def _compute_executable_from_tree(self, tree: ast.AST) -> set[int]:
        """Compute the executable line set from an already-parsed AST.

        Extracted from ``get_executable_lines`` so that ``analyze`` can reuse
        the same logic without a second ``ast.parse`` call.
        """
        result: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.stmt):
                result.add(node.lineno)
            # Decorator lines: Python evaluates decorators at definition time,
            # so each decorator line is executable (coverage.py counts them via
            # its bytecode parser; we must add them explicitly from the AST).
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for d in node.decorator_list:
                    result.add(d.lineno)
            # except-handler lines are executable (the exception type is evaluated
            # when matching), but ast.ExceptHandler is not an ast.stmt subclass.
            if isinstance(node, ast.ExceptHandler):
                result.add(node.lineno)

        if sys.version_info >= (3, 10):
            for node in ast.walk(tree):
                if isinstance(node, ast.Match):
                    for case in node.cases:
                        result.add(case.pattern.lineno)

        return result - self._docstring_lines(tree)

    def _excluded_lines(self, tree: ast.AST, source_lines: list[str]) -> set[int]:
        """Return all line numbers excluded by ``# pragma: no cover``.

        A ``# pragma: no cover`` comment on a line excludes that line and the
        entire block it controls.  For example, placing it on a ``def`` or
        ``class`` statement excludes every line in the body; placing it on an
        ``if`` statement excludes the whole if/elif/else chain.

        Block extent is determined via four passes, mirroring coverage.py's logic:

        Pass 1 — every node whose start line carries the pragma contributes
        ``range(node.lineno, node.end_lineno + 1)`` to the excluded set.

        Pass 2 — for functions and classes, if any line from the first
        decorator through the ``def``/``class`` line is already excluded, the
        entire node (decorators + body) is also excluded.  This handles the
        common pattern of ``# pragma: no cover`` on a decorator line.

        Pass 3 — clause keywords like ``else:`` and ``finally:`` have no
        corresponding AST node, so pass 1 cannot find them.  For each
        compound statement, scan the gap between the preceding clause's last
        line and the next clause's first statement for a pragma-marked line,
        then exclude the entire following clause body.

        Pass 4 — pragmas on continuation lines of multi-line statements (e.g.
        the closing ``)`` of a multi-line ``raise``) are mapped back to the
        statement's opening line.
        """
        pragma_lines = self._pragma_lines(source_lines)
        if not pragma_lines:
            return set()
        excluded = self._exclude_pragma_nodes(tree, pragma_lines)
        self._propagate_decorator_exclusions(tree, excluded)
        self._exclude_clause_keywords(tree, pragma_lines, excluded)
        self._exclude_continuation_pragmas(tree, pragma_lines, excluded)
        return excluded

    def _pragma_lines(self, source_lines: list[str]) -> set[int]:
        """Return the 1-based line numbers that carry a ``# pragma: no cover`` marker."""
        return {
            i + 1
            for i, line in enumerate(source_lines)
            # TODO - maybe use a regex here, because if casing or spacing changes, this is not enough
            if "# pragma: no cover" in line or "# pragma: nocover" in line
        }

    def _exclude_pragma_nodes(self, tree: ast.AST, pragma_lines: set[int]) -> set[int]:
        """Pass 1 — exclude every AST node whose start line carries a pragma.

        For compound statements (``if``/``for``/``while``/``try``), only the
        node's own body is excluded (up to ``body[-1].end_lineno``), not the
        entire elif/else chain, mirroring coverage.py's indent-tracking.
        """
        excluded: set[int] = set()
        for node in ast.walk(tree):
            lineno = getattr(node, "lineno", None)
            if lineno is None or lineno not in pragma_lines:
                continue
            body = getattr(node, "body", None)
            if body and isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try)):
                end = body[-1].end_lineno
            else:
                end = getattr(node, "end_lineno", lineno)
            excluded.update(range(lineno, end + 1))
        return excluded

    def _propagate_decorator_exclusions(self, tree: ast.AST, excluded: set[int]) -> None:
        """Pass 2 — propagate decorator-line exclusions into the full function/class body.

        If any line from the first decorator through the ``def``/``class`` line
        is already excluded, the entire node (decorators + body) is excluded.
        Mirrors coverage.py parser.py lines 225-228.
        """
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            first_line = min((d.lineno for d in node.decorator_list), default=node.lineno)
            if excluded.intersection(range(first_line, node.lineno + 1)):
                excluded.update(range(first_line, (node.end_lineno or node.lineno) + 1))

    def _exclude_clause_keywords(self, tree: ast.AST, pragma_lines: set[int], excluded: set[int]) -> None:
        """Pass 3 — exclude ``else:``/``finally:`` clauses marked with a pragma.

        These keywords have no corresponding AST node, so pass 1 cannot find
        them.  The keyword line falls in the gap between the preceding clause's
        last line and the first statement of the next clause; if a pragma is
        found there, the entire following clause body is excluded.
        """
        def _exclude_clause_if_marked(
            prev_nodes: Sequence[ast.AST], next_nodes: Sequence[ast.AST],
        ) -> None:
            prev_end = max(getattr(n, "end_lineno", getattr(n, "lineno", 0)) for n in prev_nodes)
            next_start = next_nodes[0].lineno  # type: ignore[attr-defined]
            for ln in range(prev_end + 1, next_start):
                if ln in pragma_lines:
                    next_end = max(getattr(n, "end_lineno", getattr(n, "lineno", 0)) for n in next_nodes)
                    excluded.update(range(ln, next_end + 1))
                    break

        for node in ast.walk(tree):
            # else: after if (not elif — elif is its own ast.If node handled by pass 1)
            if isinstance(node, ast.If) and node.orelse and not isinstance(node.orelse[0], ast.If):
                _exclude_clause_if_marked(node.body, node.orelse)
            # else: after for / while
            elif isinstance(node, (ast.For, ast.While)) and node.orelse:
                _exclude_clause_if_marked(node.body, node.orelse)
            # else: / finally: after try
            elif isinstance(node, ast.Try):
                if node.orelse:
                    _exclude_clause_if_marked(
                        list(node.body) + list(node.handlers), node.orelse
                    )
                if node.finalbody:
                    _exclude_clause_if_marked(
                        list(node.body) + list(node.handlers) + list(node.orelse),
                        node.finalbody,
                    )

    def _exclude_continuation_pragmas(self, tree: ast.AST, pragma_lines: set[int], excluded: set[int]) -> None:
        """Pass 4 — map pragmas on continuation lines back to their statement.

        Example: ``raise Foo(\\n    msg\\n)  # pragma: no cover`` — the pragma
        is on the closing ``)`` but ``ast.Raise.lineno`` points to the opening
        ``raise`` line.  coverage.py normalises via its multiline map; we
        replicate that by finding the innermost ``ast.stmt`` (or
        ``ExceptHandler``) that spans the pragma line without starting there.
        """
        matched_linenos: set[int] = set()
        for node in ast.walk(tree):
            ln = getattr(node, "lineno", None)
            if isinstance(ln, int) and ln in pragma_lines:
                matched_linenos.add(ln)
        unmatched = pragma_lines - matched_linenos
        if not unmatched:
            return

        stmts_and_handlers: list[tuple[int, int, ast.stmt | ast.ExceptHandler]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.stmt, ast.ExceptHandler)):
                ln = getattr(node, "lineno", None)
                end = getattr(node, "end_lineno", ln)
                if ln is not None and end is not None:
                    stmts_and_handlers.append((ln, end, node))

        for pragma_line in unmatched:
            best: ast.stmt | ast.ExceptHandler | None = None
            best_span = float("inf")
            for ln, end, node in stmts_and_handlers:
                if ln < pragma_line <= end:  # strictly contains (not starts at)
                    span = end - ln
                    if span < best_span:
                        best_span = span
                        best = node
            if best is not None:
                b = getattr(best, "body", None)
                if b and isinstance(best, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try)):
                    eff_end = b[-1].end_lineno or best.lineno
                else:
                    eff_end = best.end_lineno or best.lineno
                excluded.update(range(best.lineno, eff_end + 1))

    def _docstring_lines(self, tree: ast.AST) -> set[int]:
        """Return all line numbers occupied by docstrings.

        A docstring is the first statement of a module, class, or function body
        when that statement is a bare string-literal expression.  Multi-line
        docstrings contribute every line from their opening to closing quote.
        """
        result: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = node.body
            if not body:
                continue
            first = body[0]
            if not isinstance(first, ast.Expr):
                continue
            if not isinstance(first.value, ast.Constant) or not isinstance(first.value.value, str):
                continue
            end = getattr(first, "end_lineno", first.lineno)
            result.update(range(first.lineno, end + 1))
        return result
