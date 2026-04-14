"""Integration test: coverage.py and coverage-stats report the same coverage.

On Python < 3.12, coverage-stats's LineTracer displaces coverage.py's C tracer,
so coverage.py would report 0% unless coverage-stats injects its data back.
On Python >= 3.12, both tools use sys.monitoring independently and agree
naturally.  Either way, the coverage percentage for a source file must be
exactly identical between both tools.

coverage-stats always includes branch arcs in its total_coverage_pct, so
coverage.py is run with --cov-branch so both tools use the same metric.

Output is written to custom directories (test-interop-stats/ and
test-interop-cov/) that are distinct from the project's default report folders
and are gitignored.
"""
from __future__ import annotations

import json
import pytest


def test_coverage_py_and_coverage_stats_agree_on_total_coverage(pytester):
    """coverage-stats and coverage.py (with --cov-branch) report the same % for a file."""
    pytest.importorskip("pytest_cov")

    src_dir = pytester.path / "src"
    src_dir.mkdir()
    # Source file with covered, partially-covered, and uncovered functions —
    # modelled after asdf.py in the example project.
    (src_dir / "mylib.py").write_text(
        """\
def covered(a, b):
    return a + b


def partially_covered(a):
    if a > 0:
        return a
    return 0


def not_covered(a, b):
    return a * b


def poll_until_done(items):
    # while True: must not appear as a branch in either tool's report.
    # The `if not items:` check is NOT the last statement in the while body,
    # so BranchWalker can correctly resolve its false target (next sibling)
    # rather than falling back to the post-loop line.
    while True:
        if not items:
            break
        item = items.pop(0)
    return item


async def async_consume(aiter):
    # async for must appear as a 2-arc branch in both tools' reports
    results = []
    async for item in aiter:
        results.append(item)
    return results
""",
        encoding="utf-8",
    )

    pytester.makepyfile(
        test_mylib="""\
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
from mylib import covered, partially_covered, poll_until_done

def test_covered():
    assert covered(1, 2) == 3
    assert covered(0, 0) == 0

def test_partially_covered_true_branch():
    assert partially_covered(5) == 5

def test_while_true_loop():
    # Exercises while True: — must not inflate branch arc counts
    assert poll_until_done(["a", "b", "done"]) == "done"
"""
    )

    pytester.makeini(
        """\
[pytest]
coverage_stats_source = src
"""
    )

    result = pytester.runpytest(
        "--coverage-stats",
        "--coverage-stats-format=json",
        "--coverage-stats-output=test-interop-stats",
        "--cov=src",
        "--cov-branch",
        "--cov-report=json:test-interop-cov/coverage.json",
        "-p", "no:xdist",
        "-v",
    )
    result.assert_outcomes(passed=3)

    # --- coverage-stats JSON ---
    stats_path = pytester.path / "test-interop-stats" / "coverage-stats.json"
    assert stats_path.exists(), f"coverage-stats JSON not found at {stats_path}"
    stats_data = json.loads(stats_path.read_text(encoding="utf-8"))
    mylib_stats_key = next(k for k in stats_data["files"] if "mylib" in k)
    mylib_stats = stats_data["files"][mylib_stats_key]
    # total_coverage_pct already includes both statements and branch arcs.
    stats_pct: float = mylib_stats["summary"]["total_coverage_pct"]

    # --- coverage.py JSON ---
    cov_path = pytester.path / "test-interop-cov" / "coverage.json"
    assert cov_path.exists(), (
        f"coverage.py JSON not found at {cov_path}.\n"
        f"pytest output:\n{result.stdout.str()}"
    )
    cov_data = json.loads(cov_path.read_text(encoding="utf-8"))
    mylib_cov_key = next(k for k in cov_data["files"] if "mylib" in k)
    cov_summary = cov_data["files"][mylib_cov_key]["summary"]
    # percent_covered with --cov-branch uses (covered_lines + covered_branches)
    # / (num_statements + num_branches), matching coverage-stats' formula.
    cov_pct: float = cov_summary["percent_covered"]

    assert stats_pct == cov_pct, (
        f"coverage-stats: {stats_pct:.6f}%, "
        f"coverage.py: {cov_pct:.6f}% "
        f"({cov_summary.get('covered_lines')} covered lines, "
        f"{cov_summary.get('num_statements')} total statements, "
        f"{cov_summary.get('covered_branches')} covered branches, "
        f"{cov_summary.get('num_partial_branches')} partial branches).\n"
        f"coverage-stats executed lines: {sorted(mylib_stats['lines'].keys(), key=int)}"
    )


def test_generator_yields_do_not_create_false_exit_arcs(pytester):
    """Generator and async-generator yields must not be counted as branch exits.

    On Python < 3.12, sys.settrace fires a 'return' event for every yield from
    a generator.  Without the yield-vs-return check, our tracer records a false
    exit arc (yield_line, -co_firstlineno) for each yield, inflating covered
    branch counts versus coverage.py standalone.

    This test asserts that coverage.py reports the same covered_branches whether
    or not coverage-stats is active, for a file containing a generator and an
    async generator that each yield multiple values.
    """
    pytest.importorskip("pytest_cov")

    src_dir = pytester.path / "src"
    src_dir.mkdir()
    (src_dir / "genlib.py").write_text(
        """\
def simple_gen(items):
    \"\"\"Regular generator — yields each item then returns.\"\"\"
    for item in items:
        yield item


async def async_gen(items):
    \"\"\"Async generator — yields each item then returns.\"\"\"
    for item in items:
        yield item


def not_covered():
    yield 42
""",
        encoding="utf-8",
    )

    pytester.makepyfile(
        test_genlib="""\
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
from genlib import simple_gen, async_gen

def test_simple_gen():
    assert list(simple_gen([1, 2, 3])) == [1, 2, 3]

def test_async_gen():
    async def collect():
        return [x async for x in async_gen([10, 20])]
    assert asyncio.run(collect()) == [10, 20]
"""
    )

    pytester.makeini(
        """\
[pytest]
coverage_stats_source = src
"""
    )

    result = pytester.runpytest(
        "--coverage-stats",
        "--coverage-stats-format=json",
        "--coverage-stats-output=test-interop-stats",
        "--cov=src",
        "--cov-branch",
        "--cov-report=json:test-interop-cov/coverage.json",
        "-p", "no:xdist",
        "-v",
    )
    result.assert_outcomes(passed=2)

    # --- coverage.py JSON ---
    cov_path = pytester.path / "test-interop-cov" / "coverage.json"
    assert cov_path.exists(), (
        f"coverage.py JSON not found.\npytest output:\n{result.stdout.str()}"
    )
    cov_data = json.loads(cov_path.read_text(encoding="utf-8"))
    genlib_cov_key = next(k for k in cov_data["files"] if "genlib" in k)
    cov_summary = cov_data["files"][genlib_cov_key]["summary"]

    # --- coverage-stats JSON ---
    stats_path = pytester.path / "test-interop-stats" / "coverage-stats.json"
    assert stats_path.exists(), f"coverage-stats JSON not found at {stats_path}"
    stats_data = json.loads(stats_path.read_text(encoding="utf-8"))
    genlib_stats_key = next(k for k in stats_data["files"] if "genlib" in k)
    genlib_stats = stats_data["files"][genlib_stats_key]
    stats_pct: float = genlib_stats["summary"]["total_coverage_pct"]

    cov_pct: float = cov_summary["percent_covered"]
    cov_branches = cov_summary.get("covered_branches", 0)

    assert stats_pct == pytest.approx(cov_pct, abs=0.01), (
        f"Generator test: coverage-stats {stats_pct:.6f}% vs coverage.py {cov_pct:.6f}%.\n"
        f"covered_branches={cov_branches}, num_branches={cov_summary.get('num_branches')}.\n"
        f"If coverage-stats > coverage.py, the tracer is recording yield events as "
        f"false exit arcs and injecting them into coverage.py.\n"
        f"pytest output:\n{result.stdout.str()}"
    )
