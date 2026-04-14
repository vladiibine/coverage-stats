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


def test_code_asserts_not_counted_as_incidental_asserts(pytester):
    """Assert statements inside production code must NOT be counted as test asserts.

    pytest_assertion_pass only fires for pytest-rewritten assertions (test files).
    A plain `assert` in a library function is not rewritten, so it must not
    inflate incidental_asserts beyond the number of asserts in the test itself.
    """
    # Production code with 3 assert statements
    pytester.makepyfile(
        mylib="""
def validate(x):
    assert isinstance(x, int), "must be int"
    assert x >= 0, "must be non-negative"
    assert x < 1000, "must be small"
    return x * 2
"""
    )

    # Test has exactly 1 assert statement
    pytester.makepyfile(
        test_mylib="""
from mylib import validate

def test_validate():
    assert validate(5) == 10
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

    report = __import__("json").loads(
        (pytester.path / "coverage-stats-report" / "coverage-stats.json").read_text()
    )
    lines = report["files"][
        next(k for k in report["files"] if "mylib" in k and "test_" not in k)
    ]["lines"]

    # Lines executed *inside a test call* (incidental_tests > 0) are lines 2-5 —
    # the function body. Line 1 (def statement) is traced at import time, before
    # any test runs, so it has incidental_tests == 0 and is excluded.
    in_test = {lno: ld for lno, ld in lines.items() if ld["incidental_tests"] > 0}
    assert in_test, "Expected lines executed inside a test in mylib"

    # Every line executed inside the test should report exactly 1 incidental assert
    # — the single `assert validate(5) == 10` in test_validate().
    # The 3 assert statements inside validate() must not be counted because pytest
    # does not rewrite assertions in non-test files.
    for lno, ld in in_test.items():
        assert ld["incidental_asserts"] == 1, (
            f"Line {lno}: expected incidental_asserts=1 (one test assert), "
            f"got {ld['incidental_asserts']} — production code asserts may be leaking in"
        )


def test_conftest_import_lines_are_tracked(pytester):
    """Module-level lines in libraries imported by conftest.py must appear in the report.

    When conftest.py does ``import mylib``, all module-level code in mylib runs
    before any test executes.  These are pre-test lines and must be recorded even
    though they never run during a test call phase.

    Without the early-tracer fix (starting the tracer in pytest_load_initial_conftests
    with a sys.meta_path ensurer), these lines were invisible to coverage-stats because
    the tracer was not yet installed when conftest.py was imported.
    """
    # No leading blank line so line numbers are predictable:
    # 1: import os
    # 2: CONSTANT = 42
    # 3: class MyClass:
    # 4:     pass
    # 5: def helper():
    # 6:     return CONSTANT
    pytester.makepyfile(
        mylib="import os\nCONSTANT = 42\nclass MyClass:\n    pass\ndef helper():\n    return CONSTANT\n"
    )

    # conftest.py imports mylib at module level — this is the pattern that was broken.
    pytester.makeconftest("import mylib\n")

    pytester.makepyfile(
        test_mylib="from mylib import helper\ndef test_helper():\n    assert helper() == 42\n"
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

    report = json.loads(
        (pytester.path / "coverage-stats-report" / "coverage-stats.json").read_text()
    )
    mylib_key = next(
        (k for k in report["files"] if "mylib" in k and "test_" not in k and "conftest" not in k),
        None,
    )
    assert mylib_key, f"mylib not found in report: {list(report['files'].keys())}"

    lines = report["files"][mylib_key]["lines"]
    covered = {int(ln) for ln, ld in lines.items() if ld["incidental_executions"] > 0 or ld["deliberate_executions"] > 0}

    # Lines 1 (import os), 2 (CONSTANT = 42), 3 (class MyClass:) execute ONLY at
    # import time via conftest.py — they are never called during a test.  These
    # must appear as covered pre-test lines.
    import_only_lines = {1, 2, 3}
    missing = import_only_lines - covered
    assert not missing, (
        f"Module-level lines executed at conftest import time are missing from the report: {missing}. "
        f"Covered lines: {sorted(covered)}"
    )


def test_coverage_stats_source_cli_option_overrides_ini(pytester):
    """--coverage-stats-source restricts tracing to the given directory.

    Even if coverage_stats_source is not set in the ini (falling back to
    rootdir), passing --coverage-stats-source on the command line must limit
    tracking to only the specified source directory.  Files outside it (e.g.
    a conftest.py at the project root) must not appear in the report.
    """
    src_dir = pytester.path / "mypackage"
    src_dir.mkdir()
    (src_dir / "core.py").write_text("def add(a, b):\n    return a + b\n")

    # conftest.py at the project root — must NOT appear in the report
    # when --coverage-stats-source=mypackage is passed.
    pytester.makeconftest("# root conftest — should not be tracked\nROOT = True\n")

    pytester.makepyfile(
        test_core="""\
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mypackage.core import add

def test_add():
    assert add(1, 2) == 3
"""
    )

    # No coverage_stats_source in ini — would fall back to rootdir without the CLI flag.
    pytester.makeini(
        """\
[pytest]
coverage_stats_format = json
coverage_stats_output_dir = coverage-stats-report
"""
    )

    result = pytester.runpytest(
        "--coverage-stats",
        "--coverage-stats-source=mypackage",
        "-v",
    )
    result.assert_outcomes(passed=1)

    report = json.loads(
        (pytester.path / "coverage-stats-report" / "coverage-stats.json").read_text()
    )
    files = report["files"]

    pkg_keys = [k for k in files if "core" in k]
    assert pkg_keys, f"mypackage/core.py not found in report: {list(files.keys())}"

    conftest_keys = [k for k in files if "conftest" in k]
    assert not conftest_keys, (
        f"conftest.py should not be tracked when --coverage-stats-source=mypackage is set, "
        f"but found: {conftest_keys}"
    )
