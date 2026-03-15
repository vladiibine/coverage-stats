from __future__ import annotations

import json

import pytest

xdist = pytest.importorskip("xdist")


def test_xdist_two_workers_produce_merged_json(pytester):
    """Run a two-worker xdist session and assert the JSON report is merged."""
    # Create a simple source module that both tests will exercise
    pytester.makepyfile(
        myapp="""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
"""
    )

    # Two test files — each exercises the source module
    pytester.makepyfile(
        test_worker_a="""
from myapp import add

def test_add():
    assert add(1, 2) == 3
"""
    )

    pytester.makepyfile(
        test_worker_b="""
from myapp import subtract

def test_subtract():
    assert subtract(5, 3) == 2
"""
    )

    # Minimal ini so the plugin knows which source to trace
    pytester.makeini(
        """
[pytest]
coverage_stats_source = .
coverage_stats_format = json
coverage_stats_output_dir = coverage-stats-report
"""
    )

    result = pytester.runpytest(
        "--coverage-stats",
        "-n2",
        "--coverage-stats-format=json",
        "-v",
    )

    result.assert_outcomes(passed=2)

    # Locate the JSON report
    report_dir = pytester.path / "coverage-stats-report"
    json_files = list(report_dir.glob("*.json"))
    assert json_files, f"No JSON report found in {report_dir}"

    report = json.loads(json_files[0].read_text())

    # The report must contain the canonical "files" key
    assert "files" in report, f"JSON report missing 'files' key: {report}"
    files = report["files"]

    # At least one source file must be present (workers contributed data)
    myapp_keys = [k for k in files if "myapp" in k]
    assert myapp_keys, f"myapp source not found in report: {list(files.keys())}"

    myapp_lines = files[myapp_keys[0]]["lines"]
    # Both add() and subtract() run in different workers — at least 2 executed lines expected
    executed = [lno for lno, ld in myapp_lines.items()
                if ld["incidental_executions"] > 0 or ld["deliberate_executions"] > 0]
    assert len(executed) >= 2, (
        f"Expected >=2 executed lines from both workers, got {executed}"
    )
