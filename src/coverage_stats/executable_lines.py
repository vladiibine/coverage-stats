from __future__ import annotations

import ast


def get_executable_lines(path: str) -> set[int]:
    """Return the set of line numbers that contain executable statements in *path*.

    Uses AST-based statement detection (same approach as coverage.py): parses
    the source and collects the start line of every ``ast.stmt`` node.  This
    correctly handles multi-line expressions and comprehensions — a
    ``y = {x: x**2 for x in range(3)}`` spanning five lines contributes only
    one executable line (the assignment), not five.  Docstrings (the first
    string-literal expression in a module/class/function body) are excluded.

    Returns an empty set if the file cannot be read or compiled.
    """
    try:
        source = open(path, encoding="utf-8", errors="replace").read()
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return set()

    result: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            result.add(node.lineno)

    return result - _docstring_lines(tree)


def _docstring_lines(tree: ast.AST) -> set[int]:
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
