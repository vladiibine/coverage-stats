from __future__ import annotations

import ast
import sys
from dataclasses import dataclass


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
            source = open(path, encoding="utf-8", errors="replace").read()
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            return None
        return FileAnalysis(
            path=path,
            tree=tree,
            source_lines=source.splitlines(),
            executable_lines=self._compute_executable_from_tree(tree),
        )

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

        if sys.version_info >= (3, 10):
            for node in ast.walk(tree):
                if isinstance(node, ast.Match):
                    for case in node.cases:
                        result.add(case.pattern.lineno)

        return result - self._docstring_lines(tree)

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
