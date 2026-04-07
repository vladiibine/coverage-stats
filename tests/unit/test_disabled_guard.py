"""Verify that every pytest_* method on CoverageStatsPlugin starts with
`if not self._enabled: return` as its very first statement.

The test inspects the class via the AST rather than running the methods,
so it catches missing guards at definition time regardless of runtime state.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

from coverage_stats.plugin import CoverageStatsPlugin


def test_all_pytest_hooks_have_disabled_guard():
    def _is_disabled_guard(node: ast.stmt) -> bool:
        """Return True if *node* is exactly `if not self._enabled: return`."""
        if not isinstance(node, ast.If):
            return False
        test = node.test
        if not isinstance(test, ast.UnaryOp) or not isinstance(test.op, ast.Not):
            return False
        operand = test.operand
        if not isinstance(operand, ast.Attribute) or operand.attr != "_enabled":
            return False
        if not isinstance(operand.value, ast.Name) or operand.value.id != "self":
            return False
        if len(node.body) != 1 or not isinstance(node.body[0], ast.Return):
            return False
        if node.body[0].value is not None:
            return False
        if node.orelse:
            return False
        return True

    missing = []
    for name, func in inspect.getmembers(CoverageStatsPlugin, predicate=inspect.isfunction):
        if not name.startswith("pytest_"):
            continue
        source = textwrap.dedent(inspect.getsource(func))
        tree = ast.parse(source)
        func_def = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        # Skip an optional leading docstring before checking for the guard.
        body = func_def.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        if not body or not _is_disabled_guard(body[0]):
            missing.append(name)

    assert not missing, (
        f"The following pytest_* methods are missing `if not self._enabled: return` "
        f"as their first statement: {missing}"
    )
