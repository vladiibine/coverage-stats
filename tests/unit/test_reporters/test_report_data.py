from __future__ import annotations

import pytest

from coverage_stats import covers
from coverage_stats.reporters.models import FileSummary
from coverage_stats.reporters.report_data import DefaultReportBuilder


def _make_fs(
    rel_path: str = "src/a.py",
    total_stmts: int = 10,
    arcs_total: int = 0,
    deliberate_asserts: int = 0,
    incidental_asserts: int = 0,
) -> FileSummary:
    return FileSummary(
        rel_path=rel_path,
        abs_path=rel_path,
        total_stmts=total_stmts,
        total_covered=0,
        deliberate_covered=0,
        incidental_covered=0,
        arcs_total=arcs_total,
        arcs_covered=0,
        arcs_deliberate=0,
        arcs_incidental=0,
        total_pct=0.0,
        deliberate_pct=0.0,
        incidental_pct=0.0,
        partial_count=0,
        deliberate_asserts=deliberate_asserts,
        incidental_asserts=incidental_asserts,
    )


# ---------------------------------------------------------------------------
# FileSummary.to_index_row
# ---------------------------------------------------------------------------


@covers(FileSummary.to_index_row)
def test_file_to_index_row_total_stmts_includes_arcs():
    """total_stmts in IndexRowData must be statements + branches, not statements alone."""
    row = _make_fs(total_stmts=10, arcs_total=3).to_index_row()
    assert row.total_stmts == 13


@covers(FileSummary.to_index_row)
def test_file_to_index_row_total_stmts_no_arcs():
    """When there are no branches, total_stmts equals the statement count."""
    row = _make_fs(total_stmts=10, arcs_total=0).to_index_row()
    assert row.total_stmts == 10


@covers(FileSummary.to_index_row)
def test_file_to_index_row_del_assert_density_uses_stmts_plus_arcs():
    """Deliberate assert density must equal deliberate_asserts / (stmts + arcs)."""
    row = _make_fs(total_stmts=10, arcs_total=3, deliberate_asserts=6).to_index_row()
    assert row.del_assert_density == pytest.approx(6 / 13)


@covers(FileSummary.to_index_row)
def test_file_to_index_row_inc_assert_density_uses_stmts_plus_arcs():
    """Incidental assert density must equal incidental_asserts / (stmts + arcs)."""
    row = _make_fs(total_stmts=10, arcs_total=3, incidental_asserts=4).to_index_row()
    assert row.inc_assert_density == pytest.approx(4 / 13)


@covers(FileSummary.to_index_row)
def test_file_to_index_row_density_and_stmts_are_consistent():
    """del_assert_density must equal deliberate_asserts / total_stmts (after the fix)."""
    row = _make_fs(total_stmts=10, arcs_total=5, deliberate_asserts=3).to_index_row()
    assert row.total_stmts == 15
    assert row.del_assert_density == pytest.approx(row.deliberate_asserts / row.total_stmts)


@covers(FileSummary.to_index_row)
def test_file_to_index_row_zero_denom_density_is_zero():
    """When both stmts and arcs are 0, density must be 0.0 (no ZeroDivisionError)."""
    row = _make_fs(total_stmts=0, arcs_total=0, deliberate_asserts=5).to_index_row()
    assert row.del_assert_density == 0.0
    assert row.inc_assert_density == 0.0


# ---------------------------------------------------------------------------
# FolderNode.to_index_row
# ---------------------------------------------------------------------------


@covers(FileSummary.to_index_row)  # FolderNode.to_index_row has no @covers target yet
def test_folder_to_index_row_total_stmts_includes_arcs():
    """Folder total_stmts must aggregate statements + branches across all children."""
    summaries = [
        _make_fs("src/a.py", total_stmts=10, arcs_total=3),
        _make_fs("src/b.py", total_stmts=7, arcs_total=2),
    ]
    folder = DefaultReportBuilder().build_folder_tree(summaries)
    row = folder.to_index_row()
    assert row.total_stmts == 22  # (10+3) + (7+2)


@covers(FileSummary.to_index_row)
def test_folder_to_index_row_density_and_stmts_are_consistent():
    """Folder density must equal asserts / total_stmts (the displayed value)."""
    summaries = [
        _make_fs("src/a.py", total_stmts=10, arcs_total=3, deliberate_asserts=6),
        _make_fs("src/b.py", total_stmts=7, arcs_total=2, deliberate_asserts=2),
    ]
    folder = DefaultReportBuilder().build_folder_tree(summaries)
    row = folder.to_index_row()
    # total_stmts = 22, deliberate_asserts = 8 → density = 8/22
    assert row.total_stmts == 22
    assert row.deliberate_asserts == 8
    assert row.del_assert_density == pytest.approx(8 / 22)
    # The key consistency check: density == asserts / total_stmts
    assert row.del_assert_density == pytest.approx(row.deliberate_asserts / row.total_stmts)
