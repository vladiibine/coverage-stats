from __future__ import annotations

import sys
import textwrap

import pytest

from coverage_stats.store import LineData
from coverage_stats.reporters.html import _get_partial_branches
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
    result = _get_partial_branches(path, lines)
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
    result = _get_partial_branches(path, lines)
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
    result = _get_partial_branches(path, lines)
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
    result = _get_partial_branches(path, lines)
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
    result = _get_partial_branches(path, lines)
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
    result = _get_partial_branches(path, lines)
    assert case2_line not in result
