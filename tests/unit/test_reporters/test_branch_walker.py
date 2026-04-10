from __future__ import annotations

import ast
import sys
import textwrap

import pytest

from coverage_stats import covers
from coverage_stats.store import LineData
from coverage_stats.reporters.branch_analysis import BranchDescriptor, BranchWalker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(src: str) -> ast.AST:
    return ast.parse(textwrap.dedent(src))


def _ld(ie: int = 0, de: int = 0) -> LineData:
    ld = LineData()
    ld.incidental_executions = ie
    ld.deliberate_executions = de
    return ld


def _walk(src: str, lines: dict[int, LineData]) -> list[BranchDescriptor]:
    return list(BranchWalker().walk_branches(_parse(src), lines))


# ---------------------------------------------------------------------------
# if / else
# ---------------------------------------------------------------------------


@covers(BranchWalker.walk_branches)
def test_if_else_both_taken():
    """if/else with both branches executed → one descriptor, no partial."""
    src = """\
        if x > 0:
            y = 1
        else:
            y = 0
        z = 2
    """
    # line 1: if, line 2: y=1, line 3: else (virtual), line 4: y=0, line 5: z=2
    bds = _walk(src, {1: _ld(ie=10), 2: _ld(ie=5), 4: _ld(ie=5)})
    assert len(bds) == 1
    bd = bds[0]
    assert bd.node_line == 1
    assert bd.arc_count == 2
    assert bd.true_target == 2
    assert bd.false_target == 4
    assert bd.true_taken is True
    assert bd.false_taken is True
    assert bd.is_partial is False


@covers(BranchWalker.walk_branches)
def test_if_else_only_true_taken():
    """if/else where only true branch was taken → is_partial, false_taken=False."""
    src = """\
        if x > 0:
            y = 1
        else:
            y = 0
    """
    bds = _walk(src, {1: _ld(ie=5), 2: _ld(ie=5)})
    assert len(bds) == 1
    bd = bds[0]
    assert bd.true_taken is True
    assert bd.false_taken is False
    assert bd.false_target == 4
    assert bd.is_partial is True


@covers(BranchWalker.walk_branches)
def test_if_else_only_false_taken():
    """if/else where only the else branch ran → is_partial, true_taken=False."""
    src = """\
        if x > 0:
            y = 1
        else:
            y = 0
    """
    bds = _walk(src, {1: _ld(ie=5), 4: _ld(ie=5)})
    assert len(bds) == 1
    bd = bds[0]
    assert bd.true_taken is False
    assert bd.false_taken is True
    assert bd.is_partial is True


@covers(BranchWalker.walk_branches)
def test_if_no_else_true_taken_false_not():
    """if without else where condition always true → false arc not taken, is_partial."""
    src = """\
        if x > 0:
            y = 1
        z = 2
    """
    # if_count == body_count → false_taken = False
    bds = _walk(src, {1: _ld(ie=5), 2: _ld(ie=5)})
    assert len(bds) == 1
    bd = bds[0]
    assert bd.true_taken is True
    assert bd.false_taken is False
    assert bd.false_target == 3   # next sibling: z = 2
    assert bd.is_partial is True


@covers(BranchWalker.walk_branches)
def test_if_no_else_false_taken():
    """if without else where condition sometimes false → false arc taken."""
    src = """\
        if x > 0:
            y = 1
        z = 2
    """
    # if_count (10) > body_count (7) → false_taken
    bds = _walk(src, {1: _ld(ie=10), 2: _ld(ie=7)})
    assert len(bds) == 1
    bd = bds[0]
    assert bd.true_taken is True
    assert bd.false_taken is True
    assert bd.is_partial is False


@covers(BranchWalker.walk_branches)
def test_if_no_else_no_sibling_false_target_is_none():
    """if at end of module with nothing following → false_target is None."""
    src = """\
        if x > 0:
            y = 1
    """
    bds = _walk(src, {1: _ld(ie=5), 2: _ld(ie=5)})
    assert len(bds) == 1
    assert bds[0].false_target is None


@covers(BranchWalker.walk_branches)
def test_unreached_if_not_partial():
    """if never executed → both taken=False, is_partial=False, arc_count=2."""
    src = """\
        if x > 0:
            y = 1
    """
    bds = _walk(src, {})   # no execution data
    assert len(bds) == 1
    bd = bds[0]
    assert bd.arc_count == 2
    assert bd.true_taken is False
    assert bd.false_taken is False
    assert bd.is_partial is False


# ---------------------------------------------------------------------------
# for / while
# ---------------------------------------------------------------------------


@covers(BranchWalker.walk_branches)
def test_for_loop_body_taken():
    """for loop where body ran → true_taken, false_taken depends on exit."""
    src = """\
        for i in items:
            process(i)
        done = True
    """
    # for_count (5) > body_count (5)? No, assume equal → false_taken = False
    bds = _walk(src, {1: _ld(ie=5), 2: _ld(ie=5)})
    assert len(bds) == 1
    bd = bds[0]
    assert bd.node_line == 1
    assert bd.arc_count == 2
    assert bd.true_taken is True


@covers(BranchWalker.walk_branches)
def test_while_both_branches():
    """while loop that both entered and exited normally."""
    src = """\
        while cond:
            work()
        after = True
    """
    # while_count (5) > body_count (4) → false arc taken too
    bds = _walk(src, {1: _ld(ie=5), 2: _ld(ie=4)})
    assert len(bds) == 1
    bd = bds[0]
    assert bd.true_taken is True
    assert bd.false_taken is True
    assert bd.false_target == 3


# ---------------------------------------------------------------------------
# Deliberate / incidental fields
# ---------------------------------------------------------------------------


@covers(BranchWalker.walk_branches)
def test_deliberate_true_arc():
    """True arc taken deliberately → deliberate_true=True, incidental_true=False."""
    src = """\
        if x > 0:
            y = 1
        else:
            y = 0
    """
    bds = _walk(src, {1: _ld(de=5), 2: _ld(de=5), 4: _ld(de=5)})
    bd = bds[0]
    assert bd.deliberate_true is True
    assert bd.incidental_true is False
    assert bd.deliberate_false is True
    assert bd.incidental_false is False


@covers(BranchWalker.walk_branches)
def test_incidental_true_arc():
    """True arc taken incidentally → incidental_true=True, deliberate_true=False."""
    src = """\
        if x > 0:
            y = 1
        else:
            y = 0
    """
    bds = _walk(src, {1: _ld(ie=5), 2: _ld(ie=5), 4: _ld(ie=5)})
    bd = bds[0]
    assert bd.deliberate_true is False
    assert bd.incidental_true is True
    assert bd.deliberate_false is False
    assert bd.incidental_false is True


@covers(BranchWalker.walk_branches)
def test_false_arc_no_orelse_deliberate():
    """False arc (no else) deliberate: condition run more times than body deliberately."""
    src = """\
        if x > 0:
            y = 1
        z = 2
    """
    # deliberate: condition ran 3 times, body 2 → del(if) > del(body)
    bds = _walk(src, {1: _ld(de=3), 2: _ld(de=2)})
    bd = bds[0]
    assert bd.false_taken is True
    assert bd.deliberate_false is True
    assert bd.incidental_false is False


@covers(BranchWalker.walk_branches)
def test_arc_not_taken_fields_are_false():
    """Fields for untaken arcs are always False."""
    src = """\
        if x > 0:
            y = 1
        else:
            y = 0
    """
    # only true branch taken
    bds = _walk(src, {1: _ld(ie=3, de=2), 2: _ld(ie=3, de=2)})
    bd = bds[0]
    assert bd.false_taken is False
    assert bd.deliberate_false is False
    assert bd.incidental_false is False


# ---------------------------------------------------------------------------
# Multiple branch nodes
# ---------------------------------------------------------------------------


@covers(BranchWalker.walk_branches)
def test_multiple_if_statements_yield_multiple_descriptors():
    """Two if statements yield two descriptors."""
    src = """\
        if a:
            x = 1
        if b:
            y = 2
    """
    bds = _walk(src, {1: _ld(ie=3), 2: _ld(ie=3), 3: _ld(ie=3), 4: _ld(ie=3)})
    assert len(bds) == 2
    node_lines = {bd.node_line for bd in bds}
    assert 1 in node_lines
    assert 3 in node_lines


@covers(BranchWalker.walk_branches)
def test_empty_source_yields_no_descriptors():
    """Source with no branch statements yields no descriptors."""
    src = "x = 1\ny = 2\n"
    bds = _walk(src, {1: _ld(ie=1), 2: _ld(ie=1)})
    assert bds == []


# ---------------------------------------------------------------------------
# match cases (Python 3.10+)
# ---------------------------------------------------------------------------


@covers(BranchWalker.walk_branches)
@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_non_last_case_arc_count_2():
    """Non-last match case contributes arc_count=2 (body arc + next-case arc)."""
    src = """\
        match v:
            case 1:
                x = 1
            case 2:
                x = 2
    """
    tree = _parse(src)
    # find line numbers
    case1_line = next(
        case.pattern.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Match)
        for case in node.cases
        if isinstance(case.pattern, ast.MatchValue)
        and isinstance(case.pattern.value, ast.Constant)
        and case.pattern.value.value == 1
    )
    bds = list(BranchWalker().walk_branches(tree, {case1_line: _ld(ie=5), case1_line + 1: _ld(ie=5)}))
    case1_bd = next(bd for bd in bds if bd.node_line == case1_line)
    assert case1_bd.arc_count == 2
    assert case1_bd.true_target == case1_line + 1


@covers(BranchWalker.walk_branches)
@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_last_non_wildcard_case_arc_count_1():
    """Last non-wildcard match case contributes arc_count=1."""
    src = """\
        match v:
            case 1:
                x = 1
            case 2:
                x = 2
    """
    tree = _parse(src)
    case2_line = next(
        case.pattern.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Match)
        for case in node.cases
        if isinstance(case.pattern, ast.MatchValue)
        and isinstance(case.pattern.value, ast.Constant)
        and case.pattern.value.value == 2
    )
    bds = list(BranchWalker().walk_branches(tree, {case2_line: _ld(ie=3), case2_line + 1: _ld(ie=3)}))
    case2_bd = next(bd for bd in bds if bd.node_line == case2_line)
    assert case2_bd.arc_count == 1
    assert case2_bd.false_target is None
    assert case2_bd.false_taken is False


@covers(BranchWalker.walk_branches)
@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_wildcard_last_case_skipped():
    """Wildcard last case is not yielded (always matches, no branching)."""
    src = """\
        match v:
            case 1:
                x = 1
            case _:
                x = 0
    """
    tree = _parse(src)
    wild_line = next(
        case.pattern.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Match)
        for case in node.cases
        if isinstance(case.pattern, ast.MatchAs) and case.pattern.name is None
    )
    bds = list(BranchWalker().walk_branches(tree, {}))
    assert all(bd.node_line != wild_line for bd in bds)


@covers(BranchWalker.walk_branches)
@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_last_case_taken_not_partial():
    """Last non-wildcard case reached and body ran → is_partial=False."""
    src = """\
        match v:
            case 1:
                x = 1
            case 2:
                x = 2
    """
    tree = _parse(src)
    case2_line = next(
        case.pattern.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Match)
        for i, case in enumerate(node.cases)
        if i == len(node.cases) - 1
    )
    bds = list(BranchWalker().walk_branches(tree, {case2_line: _ld(ie=3), case2_line + 1: _ld(ie=3)}))
    case2_bd = next(bd for bd in bds if bd.node_line == case2_line)
    assert case2_bd.true_taken is True
    assert case2_bd.is_partial is False


@covers(BranchWalker.walk_branches)
@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_last_case_reached_but_not_taken_is_partial():
    """Last non-wildcard case reached but body never ran → is_partial=True."""
    src = """\
        match v:
            case 1:
                x = 1
            case 2:
                x = 2
    """
    tree = _parse(src)
    case2_line = next(
        case.pattern.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Match)
        for i, case in enumerate(node.cases)
        if i == len(node.cases) - 1
    )
    # case 2 reached but body never ran
    bds = list(BranchWalker().walk_branches(tree, {case2_line: _ld(ie=3)}))
    case2_bd = next(bd for bd in bds if bd.node_line == case2_line)
    assert case2_bd.true_taken is False
    assert case2_bd.is_partial is True


@covers(BranchWalker.walk_branches)
@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_case_never_reached_not_partial():
    """Case pattern line never executed → is_partial=False."""
    src = """\
        match v:
            case 1:
                x = 1
            case 2:
                x = 2
    """
    tree = _parse(src)
    case2_line = next(
        case.pattern.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Match)
        for i, case in enumerate(node.cases)
        if i == len(node.cases) - 1
    )
    bds = list(BranchWalker().walk_branches(tree, {}))
    case2_bd = next((bd for bd in bds if bd.node_line == case2_line), None)
    assert case2_bd is not None
    assert case2_bd.is_partial is False
