"""Benchmarks for the reporting phase.

Run with:
    nox -s benchmark
"""
from __future__ import annotations

import textwrap
import types
from pathlib import Path

import pytest

from coverage_stats.executable_lines import ExecutableLinesAnalyzer
from coverage_stats.reporters.branch_analysis import BranchWalker
from coverage_stats.reporters.report_data import DefaultReportBuilder
from coverage_stats.store import LineData, SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FUNCTIONS_PER_FILE = 10
_FILES = 50


def _make_source(n_functions: int) -> str:
    """Generate a Python source file with n_functions simple functions."""
    lines = ["from __future__ import annotations\n"]
    for i in range(n_functions):
        lines.append(textwrap.dedent(f"""\
            def func_{i}(x: int) -> int:
                if x > 0:
                    result = x * 2
                else:
                    result = -x
                for j in range(x):
                    result += j
                while result > 100:
                    result //= 2
                return result

        """))
    return "\n".join(lines)


def _make_line_data(ie: int = 1, de: int = 0) -> LineData:
    ld = LineData()
    ld.incidental_executions = ie
    ld.deliberate_executions = de
    return ld


def _fake_config(rootpath: Path) -> object:
    """Minimal config object with rootpath attribute."""
    return types.SimpleNamespace(rootpath=rootpath)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic_files(tmp_path_factory):
    """Write _FILES synthetic Python source files and return their paths."""
    root = tmp_path_factory.mktemp("bench_src")
    source = _make_source(_FUNCTIONS_PER_FILE)
    paths = []
    for i in range(_FILES):
        p = root / f"module_{i:03d}.py"
        p.write_text(source, encoding="utf-8")
        paths.append(str(p))
    return paths, root


@pytest.fixture(scope="module")
def populated_store(synthetic_files):
    """SessionStore pre-populated with execution data for all synthetic files."""
    paths, _root = synthetic_files
    store = SessionStore()
    # Simulate that lines 1–(7 * _FUNCTIONS_PER_FILE) were executed in each file.
    lines_per_func = 7  # rough count per function body
    for path in paths:
        for lineno in range(1, _FUNCTIONS_PER_FILE * lines_per_func + 1):
            ld = store.get_or_create((path, lineno))
            ld.incidental_executions = 3
    return store


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def test_executable_lines_analyze(benchmark, synthetic_files):
    """ExecutableLinesAnalyzer.analyze: read + parse + compute executable lines.

    This is called once per file per reporting run.  The result is a FileAnalysis
    object that DefaultReportBuilder.build uses to avoid re-parsing.
    """
    paths, _root = synthetic_files
    analyzer = ExecutableLinesAnalyzer()
    path = paths[0]

    benchmark(lambda: analyzer.analyze(path))


def test_branch_walker_walk_branches(benchmark, synthetic_files):
    """BranchWalker.walk_branches over an already-parsed AST.

    Isolates the branch-walking cost from file I/O and parsing.
    """
    paths, _root = synthetic_files
    analyzer = ExecutableLinesAnalyzer()
    fa = analyzer.analyze(paths[0])
    assert fa is not None
    walker = BranchWalker()
    lines: dict[int, LineData] = {i: _make_line_data() for i in range(1, 80)}

    benchmark(lambda: list(walker.walk_branches(fa.tree, lines)))


def test_report_build_50_files(benchmark, synthetic_files, populated_store):
    """DefaultReportBuilder.build over 50 synthetic files.

    Measures the full reporting pipeline: analyze (read+parse), branch walk,
    line aggregation, and folder-tree construction.
    """
    _paths, root = synthetic_files
    builder = DefaultReportBuilder()
    config = _fake_config(root)

    benchmark(lambda: builder.build(populated_store, config))  # type: ignore[arg-type]


def test_report_build_single_file(benchmark, synthetic_files):
    """DefaultReportBuilder.build for a single file in isolation.

    Useful for profiling the per-file cost without the loop overhead.
    """
    paths, root = synthetic_files
    store = SessionStore()
    path = paths[0]
    for lineno in range(1, 80):
        ld = store.get_or_create((path, lineno))
        ld.incidental_executions = 2
    builder = DefaultReportBuilder()
    config = _fake_config(root)

    benchmark(lambda: builder.build(store, config))  # type: ignore[arg-type]


def test_analyze_branches_single_file(benchmark, synthetic_files):
    """DefaultReportBuilder._analyze_branches for a single file.

    Isolates branch analysis from file I/O (FileAnalysis is pre-computed).
    """
    paths, _root = synthetic_files
    analyzer = ExecutableLinesAnalyzer()
    fa = analyzer.analyze(paths[0])
    assert fa is not None
    lines: dict[int, LineData] = {i: _make_line_data() for i in range(1, 80)}
    builder = DefaultReportBuilder()

    benchmark(lambda: builder._analyze_branches(fa, lines))
