from __future__ import annotations

import json


def test_default_source_tracks_only_src_directory(pytester):
    """When coverage_stats_source is not configured, only the 'src' directory is profiled."""
    src_dir = pytester.path / "src"
    src_dir.mkdir()
    (src_dir / "mylib.py").write_text("def add(a, b):\n    return a + b\n")

    pytester.makepyfile(
        test_mylib="""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
from mylib import add

def test_add():
    assert add(1, 2) == 3
"""
    )

    # No coverage_stats_source set — should default to "src"
    pytester.makeini(
        """
[pytest]
coverage_stats_format = json
coverage_stats_output_dir = coverage-stats-report
"""
    )

    result = pytester.runpytest("--coverage-stats", "-v")
    result.assert_outcomes(passed=1)

    report_dir = pytester.path / "coverage-stats-report"
    json_files = list(report_dir.glob("*.json"))
    assert json_files, "No JSON report produced"

    report = json.loads(json_files[0].read_text())
    files = report["files"]

    # src/mylib.py should appear in the report
    src_keys = [k for k in files if "mylib" in k]
    assert src_keys, f"src/mylib not found in report: {list(files.keys())}"

    # test file must NOT appear — it lives outside src/
    test_keys = [k for k in files if "test_mylib" in k]
    assert not test_keys, f"test file should not be tracked, got: {test_keys}"


def test_default_source_falls_back_when_src_missing(pytester):
    """When coverage_stats_source is not set and 'src' doesn't exist, all files are profiled."""
    pytester.makepyfile(
        mylib="""
def add(a, b):
    return a + b
"""
    )

    pytester.makepyfile(
        test_mylib="""
from mylib import add

def test_add():
    assert add(1, 2) == 3
"""
    )

    # No coverage_stats_source and no src/ directory
    pytester.makeini(
        """
[pytest]
coverage_stats_format = json
coverage_stats_output_dir = coverage-stats-report
"""
    )

    result = pytester.runpytest("--coverage-stats", "-v")
    result.assert_outcomes(passed=1)

    report_dir = pytester.path / "coverage-stats-report"
    json_files = list(report_dir.glob("*.json"))
    assert json_files, "No JSON report produced"

    report = json.loads(json_files[0].read_text())
    files = report["files"]

    # mylib.py should appear since there's no src/ filter
    mylib_keys = [k for k in files if "mylib" in k and "test_" not in k]
    assert mylib_keys, f"mylib not found in report: {list(files.keys())}"


def test_test_counts_are_tracked(pytester):
    """incidental_tests and deliberate_tests reflect the number of distinct tests that hit each line."""
    pytester.makepyfile(
        mylib="""
def add(a, b):
    return a + b
"""
    )

    pytester.makepyfile(
        test_mylib="""
from mylib import add

def test_one():
    assert add(1, 2) == 3

def test_two():
    assert add(4, 5) == 9

def test_three():
    assert add(0, 0) == 0
"""
    )

    pytester.makeini(
        """
[pytest]
coverage_stats_source = .
coverage_stats_format = json
coverage_stats_output_dir = coverage-stats-report
"""
    )

    result = pytester.runpytest("--coverage-stats", "-v")
    result.assert_outcomes(passed=3)

    report = json.loads((pytester.path / "coverage-stats-report" / "coverage-stats.json").read_text())
    files = report["files"]
    mylib_key = next(k for k in files if "mylib" in k and "test_" not in k)
    lines = files[mylib_key]["lines"]

    executed = {lno: ld for lno, ld in lines.items() if ld["incidental_executions"] > 0}
    assert executed, "Expected executed lines"

    # All 3 tests hit add() incidentally — test count should be 3
    assert any(ld["incidental_tests"] == 3 for ld in executed.values()), (
        f"Expected incidental_tests==3 on some line, got: {executed}"
    )
    # No @covers used, so deliberate_tests must be 0 everywhere
    assert all(ld["deliberate_tests"] == 0 for ld in lines.values())


def test_incidental_asserts_are_counted(pytester):
    """Lines executed under a plain (non-@covers) assert must have incidental_asserts > 0."""
    pytester.makepyfile(
        mylib="""
def add(a, b):
    return a + b
"""
    )

    pytester.makepyfile(
        test_mylib="""
from mylib import add

def test_add():
    assert add(1, 2) == 3
"""
    )

    pytester.makeini(
        """
[pytest]
coverage_stats_source = .
coverage_stats_format = json
coverage_stats_output_dir = coverage-stats-report
"""
    )

    result = pytester.runpytest("--coverage-stats", "-v")
    result.assert_outcomes(passed=1)

    report_dir = pytester.path / "coverage-stats-report"
    json_files = list(report_dir.glob("*.json"))
    assert json_files, "No JSON report produced"

    report = json.loads(json_files[0].read_text())
    files = report["files"]

    mylib_keys = [k for k in files if "mylib" in k and "test_" not in k]
    assert mylib_keys, f"mylib not found in report: {list(files.keys())}"

    lines = files[mylib_keys[0]]["lines"]
    # Line 2 (return a + b) is executed incidentally inside an assert — must have incidental_asserts
    executed_lines = {
        lno: ld for lno, ld in lines.items()
        if ld["incidental_executions"] > 0
    }
    assert executed_lines, "No incidentally executed lines found"

    has_incidental_asserts = any(
        ld["incidental_asserts"] > 0 for ld in executed_lines.values()
    )
    assert has_incidental_asserts, (
        f"Expected incidental_asserts > 0 on executed lines, got: {executed_lines}"
    )
