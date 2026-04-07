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
""",
        encoding="utf-8",
    )

    pytester.makepyfile(
        test_mylib="""\
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
from mylib import covered, partially_covered

def test_covered():
    assert covered(1, 2) == 3
    assert covered(0, 0) == 0

def test_partially_covered_true_branch():
    assert partially_covered(5) == 5
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
