from __future__ import annotations

import json

import pytest


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
