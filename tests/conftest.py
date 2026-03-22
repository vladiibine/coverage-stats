from __future__ import annotations

import ast
import sys

import pytest


def _import_time_lines(filepath: str) -> set[int]:
    """Return line numbers that execute when a module is imported.

    These are the executable lines at module scope and class-body scope, but
    NOT lines inside function or method bodies (those only execute when called).
    """
    try:
        source = open(filepath, encoding="utf-8", errors="replace").read()
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return set()

    # Collect every executable statement line in the file.
    all_stmt_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            all_stmt_lines.add(node.lineno)

    # Subtract lines that live inside a function/method body.  The def/async-def
    # line itself is NOT subtracted — it executes at import time (it creates the
    # function object).  Only the body statements are excluded.
    in_func_body: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in node.body:
                for stmt in ast.walk(child):
                    if isinstance(stmt, ast.stmt):
                        in_func_body.add(stmt.lineno)

    return all_stmt_lines - in_func_body


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """Seed pre_test_lines with module-level lines from already-imported coverage_stats modules.

    Some coverage_stats modules are imported before the tracer starts (e.g.
    covers.py via coverage_stats/__init__.py, reporters/__init__.py via
    pytest_configure's _load_report_builder_class).  Their module-level lines
    never land in pre_test_lines through normal tracing.

    This hook runs after the plugin's own pytest_sessionstart (trylast=True),
    finds every coverage_stats.* module already in sys.modules, and adds its
    import-time lines to ctx.pre_test_lines.  _flush_pre_test_lines will then
    mark them as both incidental and deliberate, exactly as if they had been
    traced normally.
    """
    ctx = getattr(session.config, "_coverage_stats_ctx", None)
    if ctx is None:
        return

    for name, mod in list(sys.modules.items()):
        if not name.startswith("coverage_stats"):
            continue
        filepath = getattr(mod, "__file__", None)
        if not filepath or not filepath.endswith(".py"):
            continue
        for lineno in _import_time_lines(filepath):
            ctx.pre_test_lines.add((filepath, lineno))
