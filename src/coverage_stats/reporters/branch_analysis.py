from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from typing import Iterator

from coverage_stats.reporters.models import _is_wildcard_case
from coverage_stats.store import LineData


@dataclass
class BranchDescriptor:
    """Describes a single branch node and the execution state of its arcs.

    Yielded by ``BranchWalker.walk_branches`` for every ``if``/``while``/
    ``for`` statement and every non-wildcard ``match`` case in a source file.
    Both ``DefaultReportBuilder._analyze_branches`` and
    ``CoveragePyInterop.compute_arcs`` consume these to avoid duplicating
    AST-walking logic.
    """
    node_line: int
    arc_count: int             # arcs this branch contributes to arcs_total (1 or 2)
    true_target: int           # line of the true-branch's first statement
    false_target: int | None   # line of the false-branch (None when absent or unfindable)
    true_taken: bool
    false_taken: bool
    deliberate_true: bool
    deliberate_false: bool
    incidental_true: bool
    incidental_false: bool
    is_partial: bool           # True when the node was reached but not all arcs were taken


class BranchWalker:
    """Walks AST branch nodes and yields ``BranchDescriptor`` objects.

    Shared by ``DefaultReportBuilder`` and ``CoveragePyInterop`` so that
    branch-detection logic lives in exactly one place.  Override
    ``walk_branches``, ``_next_sibling_lineno``, or ``_is_wildcard_case``
    to customise branch semantics.
    """

    def walk_branches(
        self,
        tree: ast.AST,
        lines: dict[int, LineData],
    ) -> Iterator[BranchDescriptor]:
        """Yield one ``BranchDescriptor`` per branch node in *tree*.

        Covers ``if``/``while``/``for`` statements and ``match`` cases
        (Python 3.10+).  Wildcard ``match`` cases (which always match and
        have no branching) are skipped.
        """
        def _count(ln: int) -> int:
            ld = lines.get(ln)
            return (ld.incidental_executions + ld.deliberate_executions) if ld else 0

        def _del(ln: int) -> int:
            ld = lines.get(ln)
            return ld.deliberate_executions if ld else 0

        def _inc(ln: int) -> int:
            ld = lines.get(ln)
            return ld.incidental_executions if ld else 0

        parent_map: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent_map[id(child)] = node

        for node in ast.walk(tree):
            if not isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                continue
            # while True: (or any constant-truthy condition) never generates a
            # conditional jump — coverage.py doesn't count it as a branch in
            # any Python version.
            if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value:
                continue
            if_count = _count(node.lineno)
            body_lineno = node.body[0].lineno
            body_count = _count(body_lineno)
            true_taken = body_count > 0

            if node.orelse:
                orelse_lineno = node.orelse[0].lineno
                false_target: int | None = orelse_lineno
                false_taken = _count(orelse_lineno) > 0
                del_false = _del(orelse_lineno) > 0
                inc_false = _inc(orelse_lineno) > 0
            else:
                false_target = self._next_sibling_lineno(node, parent_map)
                false_taken = if_count > body_count
                del_false = _del(node.lineno) > _del(body_lineno)
                inc_false = _inc(node.lineno) > _inc(body_lineno)

            is_reached = if_count > 0
            yield BranchDescriptor(
                node_line=node.lineno,
                arc_count=2,
                true_target=body_lineno,
                false_target=false_target,
                true_taken=true_taken,
                false_taken=false_taken,
                deliberate_true=true_taken and _del(body_lineno) > 0,
                deliberate_false=false_taken and del_false,
                incidental_true=true_taken and _inc(body_lineno) > 0,
                incidental_false=false_taken and inc_false,
                is_partial=is_reached and (not true_taken or not false_taken),
            )

        if sys.version_info >= (3, 10):
            for node in ast.walk(tree):
                if not isinstance(node, ast.Match):
                    continue
                for i, case in enumerate(node.cases):
                    case_line = case.pattern.lineno
                    is_last = i == len(node.cases) - 1
                    if is_last and self._is_wildcard_case(case):
                        continue
                    case_reached = _count(case_line) > 0
                    body_lineno = case.body[0].lineno
                    body_taken = _count(body_lineno) > 0
                    if is_last:
                        yield BranchDescriptor(
                            node_line=case_line,
                            arc_count=1,
                            true_target=body_lineno,
                            false_target=None,
                            true_taken=body_taken,
                            false_taken=False,
                            deliberate_true=body_taken and _del(body_lineno) > 0,
                            deliberate_false=False,
                            incidental_true=body_taken and _inc(body_lineno) > 0,
                            incidental_false=False,
                            is_partial=case_reached and not body_taken,
                        )
                    else:
                        next_case_lineno = node.cases[i + 1].pattern.lineno
                        next_case_taken = _count(next_case_lineno) > 0
                        yield BranchDescriptor(
                            node_line=case_line,
                            arc_count=2,
                            true_target=body_lineno,
                            false_target=next_case_lineno,
                            true_taken=body_taken,
                            false_taken=next_case_taken,
                            deliberate_true=body_taken and _del(body_lineno) > 0,
                            deliberate_false=next_case_taken and _del(next_case_lineno) > 0,
                            incidental_true=body_taken and _inc(body_lineno) > 0,
                            incidental_false=next_case_taken and _inc(next_case_lineno) > 0,
                            is_partial=case_reached and (not body_taken or not next_case_taken),
                        )

    def _next_sibling_lineno(self, node: ast.AST, parent_map: dict[int, ast.AST]) -> int | None:
        """Return the line number of the first statement after *node*.

        Searches the parent's statement-body attributes in turn.  If *node* is
        the last statement in its parent's body, recurses up the tree to find
        the continuation after the enclosing block.  Returns ``None`` when
        there is no continuation (e.g. end of module).
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
            # Last statement in a loop body: the continuation is the
            # loop header (back-edge), not the next sibling of the loop.
            if attr == "body" and isinstance(parent, (ast.For, ast.AsyncFor, ast.While)):
                return parent.lineno
            return self._next_sibling_lineno(parent, parent_map)
        return None

    @staticmethod
    def _is_wildcard_case(case: ast.match_case) -> bool:
        return _is_wildcard_case(case)
