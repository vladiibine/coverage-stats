"""Unit tests for CoveragePyInterop arc-data injection path.

Tests the new path where store.has_arc_data() is True: arcs are taken
directly from SessionStore._arc_data instead of reconstructed via
BranchWalker heuristics.
"""
from __future__ import annotations

import textwrap

import pytest

from coverage_stats.reporters.coverage_py_interop import CoveragePyInterop
from coverage_stats.store import LineData, SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store_with_arcs(
    path: str,
    arcs: list[tuple[int, int]],
    lines: dict[int, int] | None = None,
) -> SessionStore:
    """Build a SessionStore pre-populated with arc data for *path*.

    Each arc in *arcs* gets incidental_executions=1.  If *lines* is given,
    those line numbers are also added with the given execution counts.
    Otherwise, the from/to lines of each arc (excluding negatives) are
    added automatically with count=1 so that executed set is non-empty.
    """
    store = SessionStore()
    if lines is not None:
        for lineno, count in lines.items():
            ld = store.get_or_create((path, lineno))
            ld.incidental_executions = count
    else:
        # Auto-populate executed lines from arcs.
        seen: set[int] = set()
        for from_line, to_line in arcs:
            for ln in (from_line, to_line):
                if ln > 0 and ln not in seen:
                    ld = store.get_or_create((path, ln))
                    ld.incidental_executions = 1
                    seen.add(ln)
    for from_line, to_line in arcs:
        ad = store.get_or_create_arc((path, from_line, to_line))
        ad.incidental_executions = 1
    return store


def _make_store_no_arcs(path: str, lines: dict[int, int]) -> SessionStore:
    """Build a SessionStore with line data only (no arc data)."""
    store = SessionStore()
    for lineno, count in lines.items():
        ld = store.get_or_create((path, lineno))
        ld.incidental_executions = count
    return store


# ---------------------------------------------------------------------------
# full_arcs_for_store — arc-data path
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not pytest.importorskip("coverage", reason="coverage.py not installed").version,
    reason="coverage.py not installed",
)
def test_full_arcs_for_store_uses_real_arcs_when_available(tmp_path):
    """When store has arc data, full_arcs_for_store emits the real arcs."""
    pytest.importorskip("coverage")
    src = tmp_path / "mod.py"
    src.write_text(textwrap.dedent("""\
        def f(x):
            if x > 0:
                return x
            return 0
    """), encoding="utf-8")

    path = str(src)
    # Arc data: entry, true branch, false branch, exits
    raw_arcs = [
        (-1, 1),   # entry to module (line 1 is def)
        (-1, 2),   # entry to f (def is line 1, body starts at 2)
        (2, 3),    # if -> return x
        (2, 4),    # if -> return 0
        (3, -1),   # return x -> exit f
        (4, -1),   # return 0 -> exit f
    ]
    store = _make_store_with_arcs(path, raw_arcs)
    assert store.has_arc_data()

    interop = CoveragePyInterop()
    result = interop.full_arcs_for_store(store)
    assert path in result
    arcs = set(result[path])
    # The real arcs should be present
    assert (2, 3) in arcs, f"Expected (2,3) in arcs, got: {arcs}"
    assert (2, 4) in arcs, f"Expected (2,4) in arcs, got: {arcs}"


def test_full_arcs_for_store_falls_back_to_heuristic_when_no_arc_data(tmp_path):
    """When store has no arc data, full_arcs_for_store falls back to heuristics."""
    src = tmp_path / "mod.py"
    src.write_text(textwrap.dedent("""\
        def f(x):
            if x > 0:
                return x
            return 0
    """), encoding="utf-8")

    path = str(src)
    store = _make_store_no_arcs(path, {1: 5, 2: 5, 3: 3, 4: 2})
    assert not store.has_arc_data()

    interop = CoveragePyInterop()
    result = interop.full_arcs_for_store(store)
    assert path in result
    # Heuristic path should produce some arcs too
    assert len(result[path]) > 0


def test_full_arcs_for_store_arc_data_path_includes_entry_exit_arcs(tmp_path):
    """Entry/exit arcs (negative line numbers) from store are preserved in output."""
    pytest.importorskip("coverage")
    src = tmp_path / "mod.py"
    src.write_text(textwrap.dedent("""\
        def f(x):
            return x + 1
    """), encoding="utf-8")

    path = str(src)
    raw_arcs = [
        (-1, 1),   # module entry
        (-1, 2),   # function entry
        (2, -1),   # function exit
        (1, -1),   # module exit
    ]
    store = _make_store_with_arcs(path, raw_arcs)
    assert store.has_arc_data()

    interop = CoveragePyInterop()
    result = interop.full_arcs_for_store(store)
    arcs = set(result[path])
    # Entry/exit arcs should be present (possibly normalized)
    # At least the function entry/exit pattern should exist
    has_negative = any(a < 0 or b < 0 for a, b in arcs)
    assert has_negative, f"Expected entry/exit arcs in: {arcs}"


def test_full_arcs_for_store_arc_path_includes_sequential_arcs(tmp_path):
    """Sequential arcs between consecutive executed lines are added."""
    pytest.importorskip("coverage")
    src = tmp_path / "mod.py"
    src.write_text(textwrap.dedent("""\
        def f():
            x = 1
            y = 2
            return x + y
    """), encoding="utf-8")

    path = str(src)
    # Only entry/exit arcs in the store (no branch-to-branch arcs)
    raw_arcs = [
        (-1, 1),   # module entry
        (-1, 2),   # function entry (def on line 1, body starts line 2)
        (4, -1),   # function exit
        (1, -1),   # module exit
    ]
    store = _make_store_with_arcs(
        path,
        raw_arcs,
        lines={1: 1, 2: 1, 3: 1, 4: 1},
    )
    assert store.has_arc_data()

    interop = CoveragePyInterop()
    result = interop.full_arcs_for_store(store)
    arcs = set(result[path])
    # Sequential arcs between lines 2->3->4 should be present
    assert (2, 3) in arcs or (3, 4) in arcs, (
        f"Expected sequential arcs in: {arcs}"
    )


def test_full_arcs_for_store_empty_store_returns_empty(tmp_path):
    """An empty store returns an empty dict."""
    store = SessionStore()
    interop = CoveragePyInterop()
    result = interop.full_arcs_for_store(store)
    assert result == {}


def test_full_arcs_for_store_arc_path_handles_missing_file():
    """Missing file path with arc data returns an empty arc list."""
    pytest.importorskip("coverage")
    path = "/nonexistent/path/to/file.py"
    store = _make_store_with_arcs(path, [(1, 2), (2, -1)])
    assert store.has_arc_data()

    interop = CoveragePyInterop()
    result = interop.full_arcs_for_store(store)
    # Should not crash; missing file gives empty or falls back
    # (either empty list or graceful heuristic fallback)
    assert path in result
    # No crash is the main assertion; result may be empty
    assert isinstance(result[path], list)


# ---------------------------------------------------------------------------
# compute_full_arcs — store kwarg
# ---------------------------------------------------------------------------


def test_compute_full_arcs_with_store_uses_arc_data(tmp_path):
    """compute_full_arcs(path, lines, store=store) uses store arc data when available."""
    pytest.importorskip("coverage")
    src = tmp_path / "mod.py"
    src.write_text(textwrap.dedent("""\
        def f(x):
            if x > 0:
                return x
            return 0
    """), encoding="utf-8")

    path = str(src)
    raw_arcs = [
        (-1, 2),   # function entry
        (2, 3),    # true branch
        (2, 4),    # false branch
        (3, -1),   # exit via return x
        (4, -1),   # exit via return 0
    ]
    store = _make_store_with_arcs(
        path, raw_arcs, lines={1: 1, 2: 5, 3: 3, 4: 2}
    )
    lines = {ln: store._data[(path, ln)] for ln in [1, 2, 3, 4]}

    interop = CoveragePyInterop()
    arcs = interop.compute_full_arcs(path, lines, store=store)
    arc_set = set(arcs)
    assert (2, 3) in arc_set, f"True branch arc missing from {arc_set}"
    assert (2, 4) in arc_set, f"False branch arc missing from {arc_set}"


def test_compute_full_arcs_without_store_falls_back_to_heuristic(tmp_path):
    """compute_full_arcs(path, lines) without store uses existing heuristic."""
    src = tmp_path / "mod.py"
    src.write_text(textwrap.dedent("""\
        def f(x):
            if x > 0:
                return x
            return 0
    """), encoding="utf-8")

    path = str(src)
    ld = LineData()
    ld.incidental_executions = 5
    lines = {1: ld, 2: ld, 3: ld, 4: ld}

    interop = CoveragePyInterop()
    arcs = interop.compute_full_arcs(path, lines)
    # Should not crash and should return some arcs
    assert isinstance(arcs, list)
    assert len(arcs) > 0
