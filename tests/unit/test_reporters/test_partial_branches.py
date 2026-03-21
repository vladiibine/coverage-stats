from __future__ import annotations

import sys
import textwrap

import pytest

from coverage_stats.store import LineData
from coverage_stats.reporters.html import _analyze_branches
from coverage_stats.executable_lines import get_executable_lines


def _ld(count: int) -> LineData:
    ld = LineData()
    ld.incidental_executions = count
    return ld


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path, src: str) -> str:
    p = tmp_path / "subject.py"
    p.write_text(textwrap.dedent(src))
    return str(p)


# ---------------------------------------------------------------------------
# get_executable_lines — case pattern lines
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_case_lines_are_executable(tmp_path):
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case 2:
                    return "two"
                case _:
                    return "other"
    """)
    exe = get_executable_lines(path)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case_lines = [i + 1 for i, line in enumerate(src) if line.strip().startswith("case ")]
    assert case_lines, "expected to find case lines in source"
    for lineno in case_lines:
        assert lineno in exe, f"case line {lineno} should be executable"


# ---------------------------------------------------------------------------
# _get_partial_branches — match statements
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_case1_always_matched_is_partial(tmp_path):
    """case 1 was always matched → next case never tried → case 1 line is partial."""
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case 2:
                    return "two"
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case1_line = next(i + 1 for i, l in enumerate(src) if "case 1" in l)
    case1_body = case1_line + 1
    case2_line = next(i + 1 for i, l in enumerate(src) if "case 2" in l)

    lines = {
        case1_line: _ld(5),   # case 1 reached
        case1_body: _ld(5),   # case 1 body ran (always matched)
        # case2_line: never reached → no entry
    }
    result = _analyze_branches(path, lines).partial
    assert case1_line in result
    assert case2_line not in result  # missing, not partial


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_all_cases_taken_not_partial(tmp_path):
    """All cases were entered at least once → no case line is partial."""
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case 2:
                    return "two"
                case _:
                    return "other"
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case1_line = next(i + 1 for i, l in enumerate(src) if "case 1" in l)
    case2_line = next(i + 1 for i, l in enumerate(src) if "case 2" in l)
    case_wild_line = next(i + 1 for i, l in enumerate(src) if "case _" in l)

    lines = {
        case1_line: _ld(3),
        case1_line + 1: _ld(1),   # case 1 body (matched once)
        case2_line: _ld(2),
        case2_line + 1: _ld(1),   # case 2 body (matched once)
        case_wild_line: _ld(1),
        case_wild_line + 1: _ld(1),  # wildcard body (matched once)
    }
    result = _analyze_branches(path, lines).partial
    assert case1_line not in result
    assert case2_line not in result
    assert case_wild_line not in result


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_case_never_reached_not_partial(tmp_path):
    """A case whose pattern line was never executed is missing, not partial."""
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case 2:
                    return "two"
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case2_line = next(i + 1 for i, l in enumerate(src) if "case 2" in l)

    # only case 1 reached and matched; case 2 line has no entry
    case1_line = next(i + 1 for i, l in enumerate(src) if "case 1" in l)
    lines = {
        case1_line: _ld(5),
        case1_line + 1: _ld(5),
    }
    result = _analyze_branches(path, lines).partial
    assert case2_line not in result


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_case_never_matched_is_partial(tmp_path):
    """A case was reached (pattern evaluated) but never matched → body never ran → partial."""
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case 2:
                    return "two"
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case1_line = next(i + 1 for i, l in enumerate(src) if "case 1" in l)
    case2_line = next(i + 1 for i, l in enumerate(src) if "case 2" in l)

    lines = {
        case1_line: _ld(5),
        # case 1 body: never ran (pattern never matched)
        case2_line: _ld(5),
        case2_line + 1: _ld(5),
    }
    result = _analyze_branches(path, lines).partial
    assert case1_line in result


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_last_case_not_taken_is_partial(tmp_path):
    """Last case was reached but its body never ran → partial."""
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case 2:
                    return "two"
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case1_line = next(i + 1 for i, l in enumerate(src) if "case 1" in l)
    case2_line = next(i + 1 for i, l in enumerate(src) if "case 2" in l)

    lines = {
        case1_line: _ld(5),
        # case 1 body: never ran
        case2_line: _ld(5),
        # case 2 body: never ran
    }
    result = _analyze_branches(path, lines).partial
    assert case2_line in result


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_match_last_case_taken_not_partial(tmp_path):
    """Last case reached and body ran → not partial."""
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case 2:
                    return "two"
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case2_line = next(i + 1 for i, l in enumerate(src) if "case 2" in l)

    lines = {
        case2_line: _ld(3),
        case2_line + 1: _ld(3),
    }
    result = _analyze_branches(path, lines).partial
    assert case2_line not in result


# ---------------------------------------------------------------------------
# _analyze_branches — arc counting
# ---------------------------------------------------------------------------


def test_analyze_branches_if_both_taken(tmp_path):
    """if with both branches taken → no partial, arcs_total=2, arcs_covered=2."""
    path = _write(tmp_path, """\
        def f(x):
            if x > 0:
                return 1
            else:
                return 0
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    if_line = next(i + 1 for i, l in enumerate(src) if "if x" in l)
    body_line = if_line + 1
    else_body = next(i + 1 for i, l in enumerate(src) if "return 0" in l)
    lines = {
        if_line: _ld(10),
        body_line: _ld(5),
        else_body: _ld(5),
    }
    result = _analyze_branches(path, lines)
    assert if_line not in result.partial
    assert result.arcs_total == 2
    assert result.arcs_covered == 2


def test_analyze_branches_if_false_not_taken(tmp_path):
    """if with true branch only → partial, arcs_total=2, arcs_covered=1."""
    path = _write(tmp_path, """\
        def f(x):
            if x > 0:
                return 1
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    if_line = next(i + 1 for i, l in enumerate(src) if "if x" in l)
    body_line = if_line + 1
    lines = {
        if_line: _ld(5),
        body_line: _ld(5),
    }
    result = _analyze_branches(path, lines)
    assert if_line in result.partial
    assert result.arcs_total == 2
    assert result.arcs_covered == 1


def test_analyze_branches_for_body_not_taken(tmp_path):
    """for loop over empty iterable → body never ran → partial, arcs_total=2, arcs_covered=1."""
    path = _write(tmp_path, """\
        def f():
            for i in []:
                pass
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    for_line = next(i + 1 for i, l in enumerate(src) if "for i" in l)
    lines = {
        for_line: _ld(3),
        # body (pass) never ran
    }
    result = _analyze_branches(path, lines)
    assert for_line in result.partial
    assert result.arcs_total == 2
    assert result.arcs_covered == 1


def test_analyze_branches_unreached_branch_contributes_missed_arcs(tmp_path):
    """if block never reached → arcs_total=2, arcs_covered=0."""
    path = _write(tmp_path, """\
        def f(x):
            if x > 0:
                return 1
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    if_line = next(i + 1 for i, l in enumerate(src) if "if x" in l)
    lines: dict[int, LineData] = {}   # if line never executed
    result = _analyze_branches(path, lines)
    assert if_line not in result.partial
    assert result.arcs_total == 2
    assert result.arcs_covered == 0


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_analyze_branches_match_wildcard_last_case(tmp_path):
    """Wildcard last case contributes 0 arcs."""
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case _:
                    return "other"
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case1_line = next(i + 1 for i, l in enumerate(src) if "case 1" in l)
    case_wild_line = next(i + 1 for i, l in enumerate(src) if "case _" in l)
    lines = {
        case1_line: _ld(5),
        case1_line + 1: _ld(3),   # body taken sometimes
        case_wild_line: _ld(2),
        case_wild_line + 1: _ld(2),
    }
    result = _analyze_branches(path, lines)
    # non-last case 1: 2 arcs; wildcard last: 0 arcs → total=2
    assert result.arcs_total == 2
    assert case_wild_line not in result.partial


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_analyze_branches_match_non_wildcard_last_case(tmp_path):
    """Non-wildcard last case contributes 1 arc."""
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case 2:
                    return "two"
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case1_line = next(i + 1 for i, l in enumerate(src) if "case 1" in l)
    case2_line = next(i + 1 for i, l in enumerate(src) if "case 2" in l)
    lines = {
        case1_line: _ld(5),
        case1_line + 1: _ld(3),
        case2_line: _ld(2),
        case2_line + 1: _ld(2),
    }
    result = _analyze_branches(path, lines)
    # case 1 (non-last): 2 arcs; case 2 (non-wildcard last): 1 arc → total=3
    assert result.arcs_total == 3


# ---------------------------------------------------------------------------
# _analyze_branches — arcs_deliberate / arcs_incidental
# ---------------------------------------------------------------------------


def _ld_di(ie=0, de=0) -> LineData:
    ld = LineData()
    ld.incidental_executions = ie
    ld.deliberate_executions = de
    return ld


def test_analyze_branches_if_true_arc_deliberate(tmp_path):
    """Body run deliberately → true arc counted in arcs_deliberate."""
    path = _write(tmp_path, """\
        def f(x):
            if x > 0:
                return 1
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    if_line = next(i + 1 for i, l in enumerate(src) if "if x" in l)
    body_line = if_line + 1
    lines = {if_line: _ld_di(de=3), body_line: _ld_di(de=3)}
    result = _analyze_branches(path, lines)
    assert result.arcs_deliberate == 1   # true arc taken deliberately
    assert result.arcs_incidental == 0


def test_analyze_branches_if_true_arc_incidental(tmp_path):
    """Body run incidentally → true arc counted in arcs_incidental."""
    path = _write(tmp_path, """\
        def f(x):
            if x > 0:
                return 1
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    if_line = next(i + 1 for i, l in enumerate(src) if "if x" in l)
    body_line = if_line + 1
    lines = {if_line: _ld_di(ie=3), body_line: _ld_di(ie=3)}
    result = _analyze_branches(path, lines)
    assert result.arcs_deliberate == 0
    assert result.arcs_incidental == 1   # true arc taken incidentally


def test_analyze_branches_if_false_arc_no_orelse_deliberate(tmp_path):
    """Condition evaluated more times than body during deliberate tests → false arc deliberate."""
    path = _write(tmp_path, """\
        def f(x):
            if x > 0:
                return 1
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    if_line = next(i + 1 for i, l in enumerate(src) if "if x" in l)
    body_line = if_line + 1
    # deliberate: ran condition 3 times, body 2 times → false arc taken deliberately
    lines = {if_line: _ld_di(de=3), body_line: _ld_di(de=2)}
    result = _analyze_branches(path, lines)
    assert result.arcs_deliberate == 2   # both true and false arcs taken deliberately
    assert result.arcs_incidental == 0


def test_analyze_branches_if_both_arcs_deliberate_and_incidental(tmp_path):
    """Same arc taken in both deliberate and incidental tests — counted in both."""
    path = _write(tmp_path, """\
        def f(x):
            if x > 0:
                return 1
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    if_line = next(i + 1 for i, l in enumerate(src) if "if x" in l)
    body_line = if_line + 1
    lines = {if_line: _ld_di(ie=2, de=2), body_line: _ld_di(ie=2, de=2)}
    result = _analyze_branches(path, lines)
    assert result.arcs_deliberate == 1   # true arc (body covered deliberately)
    assert result.arcs_incidental == 1   # true arc (body covered incidentally)


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match requires Python 3.10+")
def test_analyze_branches_match_arc_deliberate(tmp_path):
    """Match body taken deliberately → arc counted in arcs_deliberate."""
    path = _write(tmp_path, """\
        def f(v):
            match v:
                case 1:
                    return "one"
                case 2:
                    return "two"
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    case1_line = next(i + 1 for i, l in enumerate(src) if "case 1" in l)
    case2_line = next(i + 1 for i, l in enumerate(src) if "case 2" in l)
    lines = {
        case1_line: _ld_di(de=5),
        case1_line + 1: _ld_di(de=3),   # case 1 body: deliberate
        case2_line: _ld_di(ie=2),
        case2_line + 1: _ld_di(ie=2),   # case 2 body: incidental
    }
    result = _analyze_branches(path, lines)
    # case1 body arc → deliberate; case2 body arc → incidental
    # case1 next-case arc: case2_line reached incidentally → incidental
    assert result.arcs_deliberate == 1
    assert result.arcs_incidental == 2
