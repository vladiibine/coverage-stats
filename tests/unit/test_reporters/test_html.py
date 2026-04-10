from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from coverage_stats import covers
from coverage_stats.store import SessionStore
from coverage_stats.reporters.html import HtmlReporter
from coverage_stats.reporters.html_report_helpers.file_reporter import FilePageReporter
from coverage_stats.reporters.html_report_helpers.index_reporter import IndexPageReporter
from coverage_stats.reporters.base import Reporter
from coverage_stats.reporters.models import FileSummary, FolderNode, LineReport
from coverage_stats.reporters.report_data import DefaultReportBuilder


def _make_file_summary(
    rel_path: str,
    total_stmts: int = 0,
    total_covered: int = 0,
    arcs_total: int = 0,
    arcs_covered: int = 0,
    arcs_deliberate: int = 0,
    arcs_incidental: int = 0,
    deliberate_covered: int = 0,
    incidental_covered: int = 0,
) -> FileSummary:
    total_denom = total_stmts + arcs_total
    total_pct = (total_covered + arcs_covered) / total_denom * 100.0 if total_denom else 100.0
    deliberate_pct = (deliberate_covered + arcs_deliberate) / total_denom * 100.0 if total_denom else 100.0
    incidental_pct = (incidental_covered + arcs_incidental) / total_denom * 100.0 if total_denom else 100.0
    return FileSummary(
        rel_path=rel_path,
        abs_path=rel_path,
        total_stmts=total_stmts,
        total_covered=total_covered,
        deliberate_covered=deliberate_covered,
        incidental_covered=incidental_covered,
        arcs_total=arcs_total,
        arcs_covered=arcs_covered,
        arcs_deliberate=arcs_deliberate,
        arcs_incidental=arcs_incidental,
        total_pct=total_pct,
        deliberate_pct=deliberate_pct,
        incidental_pct=incidental_pct,
        partial_count=0,
    )


def make_config(rootdir: Path) -> SimpleNamespace:
    return SimpleNamespace(rootpath=rootdir)


# ---------------------------------------------------------------------------
# write_html integration tests
# ---------------------------------------------------------------------------


@covers(HtmlReporter.write)
def test_empty_store_writes_index(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,tmp_path / "out")
    assert (tmp_path / "out" / "index.html").exists()


@covers(HtmlReporter.write)
def test_empty_store_no_per_file_pages(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    html_files = list(out_dir.glob("*.html"))
    assert html_files == [out_dir / "index.html"]


@covers(HtmlReporter.write)
def test_single_file_writes_per_file_page(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    assert (out_dir / "src__foo.py.html").exists()


@covers(HtmlReporter.write)
def test_index_contains_table_and_folder_row(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "index.html").read_text()
    assert '<table id="coverage-table">' in content
    assert "folder-row" in content


@covers(HtmlReporter.write)
def test_index_contains_folder_name(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "index.html").read_text()
    assert "src" in content


@covers(HtmlReporter.write)
def test_multiple_folders_appear_in_single_table(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    (rootdir / "src").mkdir(parents=True)
    (rootdir / "lib").mkdir(parents=True)
    store.get_or_create((str(rootdir / "src" / "a.py"), 1)).incidental_executions = 1
    store.get_or_create((str(rootdir / "lib" / "b.py"), 2)).deliberate_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "index.html").read_text()
    assert content.count('<table id="coverage-table">') == 1  # single table
    assert content.count('class="folder-row"') == 2  # one row per top-level folder


@covers(HtmlReporter.write)
def test_per_file_page_contains_lineno(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "mod.py")
    store.get_or_create((abs_file, 42)).incidental_executions = 3
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "mod.py.html").read_text()
    assert "42" in content


@covers(HtmlReporter.write)
def test_deliberate_line_gets_green_class(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "mod.py")
    store.get_or_create((abs_file, 5)).deliberate_executions = 2
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "mod.py.html").read_text()
    assert "deliberate" in content


@covers(HtmlReporter.write)
def test_incidental_only_line_gets_yellow_class(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "mod.py")
    ld = store.get_or_create((abs_file, 3))
    ld.incidental_executions = 1
    ld.deliberate_executions = 0
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "mod.py.html").read_text()
    assert "incidental" in content


@covers(HtmlReporter.write)
def test_per_file_page_shows_all_source_lines(tmp_path):
    """All lines in the source file must appear, not just covered lines."""
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    src_file = rootdir / "mod.py"
    src_file.write_text("line1\nline2\nline3\nline4\nline5\n")

    store = SessionStore()
    # Only line 3 is covered
    store.get_or_create((str(src_file), 3)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "mod.py.html").read_text()

    # Every line number 1-5 must appear
    for lineno in range(1, 6):
        assert f"<td>{lineno}</td>" in content, f"Line {lineno} missing from file page"


@covers(HtmlReporter.write)
def test_per_file_page_shows_uncovered_source_text(tmp_path):
    """Source text of uncovered lines must appear in the page."""
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    src_file = rootdir / "mod.py"
    src_file.write_text("covered_line\nuncovered_line\n")

    store = SessionStore()
    store.get_or_create((str(src_file), 1)).incidental_executions = 1
    # line 2 is NOT in the store

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "mod.py.html").read_text()

    assert "uncovered_line" in content


@covers(HtmlReporter.write)
def test_uncovered_lines_have_no_highlight_class(tmp_path):
    """Lines with no coverage data must not get the 'deliberate' or 'incidental' class."""
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    src_file = rootdir / "mod.py"
    src_file.write_text("first\nsecond\nthird\n")

    store = SessionStore()
    store.get_or_create((str(src_file), 1)).deliberate_executions = 1
    # lines 2 and 3 are uncovered

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "mod.py.html").read_text()

    # Row for uncovered line 2 should be a plain <tr> without a class attribute on it
    # We check that "second" (the source text) appears in a <tr> that has no class
    import re
    rows = re.findall(r'<tr[^>]*>.*?</tr>', content)
    uncovered_rows = [r for r in rows if "second" in r or "third" in r]
    assert uncovered_rows, "Uncovered lines not found in output"
    for row in uncovered_rows:
        assert 'class="deliberate"' not in row
        assert 'class="incidental"' not in row


@covers(HtmlReporter.write)
def test_index_stmt_count_reflects_executable_stmts_not_just_covered(tmp_path):
    """The stmt count in the index summary must equal the file's executable statements."""
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    src_file = rootdir / "mod.py"
    src_file.write_text("\n".join(f"x{i} = {i}" for i in range(1, 11)))  # 10 assignment stmts

    store = SessionStore()
    # Only 2 of 10 statements are covered
    store.get_or_create((str(src_file), 1)).deliberate_executions = 1
    store.get_or_create((str(src_file), 5)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "index.html").read_text()

    # The index must show 10 (total executable stmts), not 2 (tracked stmts)
    assert 'data-col="stmts">10</td>' in content
    assert 'data-col="stmts">2</td>' not in content


@covers(HtmlReporter.write)
def test_empty_source_file_shows_zero_stmts_in_index(tmp_path):
    """An empty (0-byte) source file must show 0 stmts in the index even if the
    tracer recorded a phantom line-1 entry for it (Python fires an implicit trace
    event when importing empty __init__.py files).  Before the fix, the fallback
    ``len(lines)`` would yield 1 instead of 0, inflating the aggregate denominator.
    """
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    pkg = rootdir / "pkg"
    pkg.mkdir()
    init_file = pkg / "__init__.py"
    init_file.write_text("")  # empty — no executable statements

    store = SessionStore()
    # Simulate the phantom trace event Python generates for empty __init__.py
    store.get_or_create((str(init_file), 1)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "index.html").read_text()

    import re
    # The file row renders as: <a href="...">__init__.py</a></td><td data-col="stmts">{stmts}</td>
    # Match the stmt count cell that immediately follows the __init__.py link.
    match = re.search(r'__init__\.py</a></td><td data-col="stmts">(\d+)</td>', content)
    assert match is not None, "__init__.py row not found in index"
    assert match.group(1) == "0", f"expected 0 stmts for empty __init__.py, got {match.group(1)}"


@covers(HtmlReporter.write)
def test_nonexistent_file_stmt_count_falls_back_to_store(tmp_path):
    """For a file that does not exist on disk, total_stmts should fall back to
    the number of lines recorded in the store (the pre-fix behaviour for
    genuinely missing files must be preserved).
    """
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    missing = str(rootdir / "missing.py")   # never created on disk

    store = SessionStore()
    store.get_or_create((missing, 3)).incidental_executions = 1
    store.get_or_create((missing, 7)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    content = (out_dir / "index.html").read_text()

    # Falls back to len(lines) = 2
    assert 'data-col="stmts">2</td>' in content


@covers(HtmlReporter.write)
def test_unreadable_source_falls_back_gracefully(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    # abs_path points to a nonexistent file
    abs_file = str(rootdir / "nonexistent.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    # Must not raise
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    assert (out_dir / "nonexistent.py.html").exists()
    content = (out_dir / "nonexistent.py.html").read_text()
    assert "1" in content


@covers(HtmlReporter.write)
def test_path_outside_rootdir_fallback(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    outside_file = str(tmp_path / "other" / "baz.py")
    store.get_or_create((outside_file, 10)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    # index.html should exist and contain the absolute path
    content = (out_dir / "index.html").read_text()
    assert "baz.py" in content


@covers(HtmlReporter.write)
def test_output_dir_created_if_missing(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    out_dir = tmp_path / "nested" / "deep" / "out"
    assert not out_dir.exists()
    report = DefaultReportBuilder().build(store, config)
    HtmlReporter().write(report,out_dir)
    assert (out_dir / "index.html").exists()


@covers(HtmlReporter)
def test_html_reporter_implements_reporter_protocol():
    """HtmlReporter must satisfy the Reporter protocol."""
    import inspect

    reporter = HtmlReporter()

    # Runtime structural check (requires @runtime_checkable on Reporter)
    assert isinstance(reporter, Reporter)

    # write() must exist and be callable
    assert callable(reporter.write)

    # Signature must match the protocol: (self, report: CoverageReport, output_dir: Path) -> None
    sig = inspect.signature(reporter.write)
    params = list(sig.parameters)
    assert params == ["report", "output_dir"]
    assert sig.return_annotation in (None, "None")


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


def _make_ld(ie=0, de=0, ia=0, da=0):
    from coverage_stats.store import LineData
    return LineData(
        incidental_executions=ie,
        deliberate_executions=de,
        incidental_asserts=ia,
        deliberate_asserts=da,
    )


@covers(HtmlReporter.render_line)
def test_render_line_deliberate_class():
    ld = _make_ld(de=1)
    result = HtmlReporter().render_line(1, "x = 1", ld, executable=True)
    assert 'class="deliberate"' in result
    assert "<td>1</td>" in result


@covers(HtmlReporter.render_line)
def test_render_line_incidental_class():
    ld = _make_ld(ie=2)
    result = HtmlReporter().render_line(7, "pass", ld, executable=True)
    assert 'class="incidental"' in result


@covers(HtmlReporter.render_line)
def test_render_line_missed_executable_gets_missed_class():
    ld = _make_ld()
    result = HtmlReporter().render_line(3, "import os", ld, executable=True)
    assert 'class="missed"' in result


@covers(HtmlReporter.render_line)
def test_render_line_non_executable_no_class():
    ld = _make_ld(de=1)
    result = HtmlReporter().render_line(3, "# comment", ld, executable=False)
    assert 'class=' not in result
    assert "<tr>" in result


@covers(HtmlReporter.render_line)
def test_render_line_missed_class():
    result = HtmlReporter().render_line(5, "x = 1", None, executable=True)
    assert 'class="missed"' in result


@covers(HtmlReporter.render_line)
def test_render_line_escapes_html():
    ld = _make_ld()
    result = HtmlReporter().render_line(1, "<script>alert(1)</script>", ld, executable=True)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


@covers(DefaultReportBuilder.build_folder_tree)
def test_build_file_tree_groups_by_folder():
    summaries = [
        _make_file_summary("src/a.py", total_stmts=10, total_covered=7, deliberate_covered=5, incidental_covered=3),
        _make_file_summary("src/sub/b.py", total_stmts=8, total_covered=5, deliberate_covered=2, incidental_covered=4),
    ]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    assert "src" in tree.subfolders
    src_node = tree.subfolders["src"]
    assert len(src_node.files) == 1
    assert src_node.files[0].rel_path == "src/a.py"
    assert "sub" in src_node.subfolders
    assert src_node.subfolders["sub"].files[0].rel_path == "src/sub/b.py"


@covers(FolderNode.compute_aggregates)
def test_folder_node_aggregates_stats():
    summaries = [
        _make_file_summary("src/a.py", total_stmts=10, total_covered=7, arcs_total=4, arcs_covered=3, arcs_deliberate=2, arcs_incidental=1, deliberate_covered=5, incidental_covered=3),
        _make_file_summary("src/sub/b.py", total_stmts=8, total_covered=5, arcs_total=2, arcs_covered=1, arcs_deliberate=1, arcs_incidental=0, deliberate_covered=2, incidental_covered=4),
    ]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    agg = tree.subfolders["src"].compute_aggregates()
    assert agg.total_stmts == 18
    assert agg.total_covered == 12
    assert agg.deliberate == 7
    assert agg.incidental == 7
    assert agg.arcs_total == 6
    assert agg.arcs_covered == 4
    assert agg.arcs_deliberate == 3
    assert agg.arcs_incidental == 1


@covers(HtmlReporter._render_tree_rows)
def test_render_tree_rows_contains_link_and_folder():
    summaries = [_make_file_summary("src/foo.py", total_stmts=3, total_covered=2, deliberate_covered=1, incidental_covered=2)]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    html = "".join(HtmlReporter()._render_tree_rows(tree, depth=0, parent_id=""))
    assert 'href="src__foo.py.html"' in html
    assert "foo.py" in html
    assert "src/" in html  # folder row


@covers(HtmlReporter._render_tree_rows)
def test_render_tree_rows_pct_calculation():
    summaries = [_make_file_summary("src/x.py", total_stmts=3, total_covered=2, deliberate_covered=1, incidental_covered=0)]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    html = "".join(HtmlReporter()._render_tree_rows(tree, depth=0, parent_id=""))
    assert "33.3%" in html  # 1/3 deliberate on file row
    assert "66.7%" in html  # 2/3 total on file row


@covers(HtmlReporter.render_index_page)
def test_render_index_page_full_html():
    result = HtmlReporter().render_index_page("<tr><td>row</td></tr>")
    assert "<!DOCTYPE html>" in result
    assert "<style>" in result
    assert "<script>" in result
    assert "<tr><td>row</td></tr>" in result
    assert '<table id="coverage-table">' in result


@covers(HtmlReporter.render_file_page)
def test_render_file_page_full_html():
    result = HtmlReporter().render_file_page("src/foo.py", "<div>stats</div>", "<tr><td>42</td></tr>")
    assert "<!DOCTYPE html>" in result
    assert "src/foo.py" in result
    assert "42" in result
    assert "stats" in result
    assert "<style>" in result


@covers(HtmlReporter.render_file_stats)
def test_render_file_stats_shows_total_pct():
    result = HtmlReporter().render_file_stats(
        total_stmts=10, covered=7, total_pct=70.0,
        deliberate_cnt=4, deliberate_pct=40.0,
        incidental_cnt=3, incidental_pct=30.0,
    )
    assert "70.0%" in result
    assert "total %" in result



@covers(HtmlReporter._render_tree_rows)
def test_render_tree_rows_total_pct_column():
    summaries = [
        _make_file_summary("src/z.py", total_stmts=4, total_covered=3, deliberate_covered=2, incidental_covered=1),
    ]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    html = "".join(HtmlReporter()._render_tree_rows(tree, depth=0, parent_id=""))
    assert "75.0%" in html   # 3/4 total on file row
    assert "50.0%" in html   # 2/4 deliberate on file row


@covers(HtmlReporter.render_index_page)
def test_index_page_has_total_pct_header():
    result = HtmlReporter().render_index_page("")
    assert "Total %" in result


# ---------------------------------------------------------------------------
# FilePageReporter._missed_ranges
# ---------------------------------------------------------------------------


@covers(FilePageReporter._missed_ranges)
def test_missed_ranges_empty():
    assert FilePageReporter()._missed_ranges([]) == ""


@covers(FilePageReporter._missed_ranges)
def test_missed_ranges_single():
    assert FilePageReporter()._missed_ranges([7]) == "7"


@covers(FilePageReporter._missed_ranges)
def test_missed_ranges_consecutive_collapsed_to_range():
    assert FilePageReporter()._missed_ranges([3, 4, 5]) == "3-5"


@covers(FilePageReporter._missed_ranges)
def test_missed_ranges_non_consecutive():
    assert FilePageReporter()._missed_ranges([1, 3, 5]) == "1, 3, 5"


@covers(FilePageReporter._missed_ranges)
def test_missed_ranges_mixed():
    assert FilePageReporter()._missed_ranges([1, 2, 5, 6, 7, 10]) == "1-2, 5-7, 10"


# ---------------------------------------------------------------------------
# DefaultReportBuilder.build_folder_tree
# ---------------------------------------------------------------------------


@covers(DefaultReportBuilder.build_folder_tree)
def test_build_folder_tree_groups_single_file():
    summaries = [_make_file_summary("src/a.py", total_stmts=1, total_covered=1, deliberate_covered=1)]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    assert "src" in tree.subfolders


@covers(DefaultReportBuilder.build_folder_tree)
def test_build_folder_tree_file_at_root_level():
    summaries = [_make_file_summary("a.py", total_stmts=1, total_covered=1, deliberate_covered=1)]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    assert len(tree.files) == 1
    assert tree.files[0].rel_path == "a.py"


# ---------------------------------------------------------------------------
# HtmlReporter CSS/JS class attributes
# ---------------------------------------------------------------------------


@covers(IndexPageReporter.render_index_page)
def test_css_class_attribute_appears_in_index():
    result = IndexPageReporter().render_index_page("")
    assert IndexPageReporter.CSS in result


@covers(IndexPageReporter.render_index_page)
def test_js_class_attribute_appears_in_index():
    result = IndexPageReporter().render_index_page("")
    assert IndexPageReporter.JS in result


@covers(IndexPageReporter.render_index_page)
def test_extra_css_empty_by_default():
    assert IndexPageReporter.EXTRA_CSS == ""


@covers(IndexPageReporter.render_index_page)
def test_extra_js_empty_by_default():
    assert IndexPageReporter.EXTRA_JS == ""


@covers(IndexPageReporter.render_index_page)
def test_extra_css_injected_when_set_on_subclass():
    class StyledReporter(IndexPageReporter):
        EXTRA_CSS = "body { background: black; }"

    result = StyledReporter().render_index_page("")
    assert "background: black" in result


@covers(IndexPageReporter.render_index_page)
def test_extra_js_injected_when_set_on_subclass():
    class TrackedReporter(IndexPageReporter):
        EXTRA_JS = "console.log('loaded');"

    result = TrackedReporter().render_index_page("")
    assert "console.log('loaded');" in result


@covers(IndexPageReporter.render_index_page)
def test_css_override_on_subclass_replaces_default():
    class MinimalReporter(IndexPageReporter):
        CSS = "body { margin: 0; }"

    result = MinimalReporter().render_index_page("")
    assert "body { margin: 0; }" in result
    assert IndexPageReporter.CSS not in result


# ---------------------------------------------------------------------------
# HtmlReporter method overrides propagate through write()
# ---------------------------------------------------------------------------


@covers(HtmlReporter.write)
def test_subclass_render_line_override_is_called(tmp_path):
    """write() must use the FilePageReporter returned by get_file_reporter().

    The canonical extension point for render_line is to subclass FilePageReporter
    and override get_file_reporter() on HtmlReporter.
    """
    from coverage_stats.reporters.html_report_helpers.file_reporter import FilePageReporter

    class MarkedFileReporter(FilePageReporter):
        def render_line(self, lineno, source_text, ld, executable, partial=False, _ranges=None) -> str:
            return f'<tr class="custom-row"><td>{lineno}</td></tr>'

    class MarkedReporter(HtmlReporter):
        def get_file_reporter(self) -> FilePageReporter:
            return MarkedFileReporter(precision=self.precision)

    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    store.get_or_create((str(rootdir / "mod.py"), 1)).incidental_executions = 1
    config = make_config(rootdir)
    report = DefaultReportBuilder().build(store, config)

    out_dir = tmp_path / "out"
    MarkedReporter().write(report, out_dir)
    content = (out_dir / "mod.py.html").read_text()
    assert "custom-row" in content


@covers(HtmlReporter.write)
def test_subclass_render_index_page_override_is_called(tmp_path):
    """write() must use the IndexPageReporter returned by get_index_reporter().

    The canonical extension point for render_index_page is to subclass IndexPageReporter
    and override get_index_reporter() on HtmlReporter.
    """
    class BrandedIndexReporter(IndexPageReporter):
        def render_index_page(self, rows_html: str) -> str:
            return f"<html><body><h1>My Company Coverage</h1>{rows_html}</body></html>"

    class BrandedReporter(HtmlReporter):
        def get_index_reporter(self) -> IndexPageReporter:
            return BrandedIndexReporter(precision=self.precision)

    store = SessionStore()
    config = make_config(tmp_path)
    report = DefaultReportBuilder().build(store, config)

    out_dir = tmp_path / "out"
    BrandedReporter().write(report, out_dir)
    content = (out_dir / "index.html").read_text()
    assert "My Company Coverage" in content


@covers(HtmlReporter.write)
def test_subclass_render_file_stats_override_is_called(tmp_path):
    """write() must use the FilePageReporter returned by get_file_reporter().

    The canonical extension point for render_file_stats is to subclass FilePageReporter
    and override get_file_reporter() on HtmlReporter.
    """
    class NoStatsFileReporter(FilePageReporter):
        def render_file_stats(self, *args, **kwargs) -> str:
            return '<div id="custom-stats"></div>'

    class NoStatsReporter(HtmlReporter):
        def get_file_reporter(self) -> FilePageReporter:
            return NoStatsFileReporter(precision=self.precision)

    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    store.get_or_create((str(rootdir / "mod.py"), 1)).incidental_executions = 1
    config = make_config(rootdir)
    report = DefaultReportBuilder().build(store, config)

    out_dir = tmp_path / "out"
    NoStatsReporter().write(report, out_dir)
    content = (out_dir / "mod.py.html").read_text()
    assert "custom-stats" in content


@covers(HtmlReporter.write)
def test_subclass_render_tree_rows_override_is_called(tmp_path):
    """write() must use the IndexPageReporter returned by get_index_reporter().

    The canonical extension point for _render_tree_rows is to subclass IndexPageReporter
    and override get_index_reporter() on HtmlReporter.
    """
    class FlatIndexReporter(IndexPageReporter):
        def _render_tree_rows(self, node, depth, parent_id, _ranges=None) -> list[str]:
            return ['<tr class="flat-row"><td>flat</td></tr>']

    class FlatReporter(HtmlReporter):
        def get_index_reporter(self) -> IndexPageReporter:
            return FlatIndexReporter(precision=self.precision)

    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    store.get_or_create((str(rootdir / "mod.py"), 1)).incidental_executions = 1
    config = make_config(rootdir)
    report = DefaultReportBuilder().build(store, config)

    out_dir = tmp_path / "out"
    FlatReporter().write(report, out_dir)
    content = (out_dir / "index.html").read_text()
    assert "flat-row" in content


# ---------------------------------------------------------------------------
# Column controls — checkboxes and data-col attributes
# ---------------------------------------------------------------------------

# Mirrors HtmlReporter.INDEX_COLUMNS — kept in sync manually so tests don't import private state
_INDEX_TOGGLEABLE_COLS = {
    "stmts": "Stmts",
    "total-pct": "Total %",
    "delib-pct": "Deliberate %",
    "incid-pct": "Incidental %",
    "delib-covered": "Del. Covered",
    "incid-covered": "Inc. Covered",
    "inc-asserts": "Inc. Asserts",
    "del-asserts": "Del. Asserts",
    "inc-assert-density": "Inc. Assert Density",
    "del-assert-density": "Del. Assert Density",
}

# Columns that can be toggled on the file page and their checkbox labels
_FILE_TOGGLEABLE_COLS = {
    "inc-exec": "Inc. Executions",
    "del-exec": "Del. Executions",
    "inc-asserts": "Inc. Asserts",
    "del-asserts": "Del. Asserts",
    "inc-tests": "Inc. Tests",
    "del-tests": "Del. Tests",
}


@covers(HtmlReporter.render_index_page)
def test_index_page_has_col_controls():
    html = HtmlReporter().render_index_page("")
    assert 'class="col-controls"' in html


@covers(HtmlReporter.render_index_page)
def test_index_col_controls_has_checkbox_for_every_toggleable_column():
    html = HtmlReporter().render_index_page("")
    for col_id in _INDEX_TOGGLEABLE_COLS:
        assert f'value="{col_id}"' in html, f"checkbox for column '{col_id}' missing from index"


@covers(HtmlReporter.render_index_page)
def test_index_checkboxes_reflect_python_defaults():
    """Checkboxes must match INDEX_COLUMNS: True → checked, False → unchecked."""
    import re
    html = HtmlReporter().render_index_page("")
    for col_id, visible in IndexPageReporter.INDEX_COLUMNS.items():
        cb = re.search(rf'<input[^>]+value="{col_id}"[^>]*>', html)
        assert cb, f"checkbox for '{col_id}' not found"
        has_checked = bool(re.search(r'\schecked\s*>', cb.group(0)))
        assert has_checked == visible, (
            f"checkbox for '{col_id}' checked={has_checked}, expected {visible}"
        )


@covers(HtmlReporter.render_index_page)
def test_index_each_toggleable_column_has_data_col_on_header():
    html = HtmlReporter().render_index_page("")
    for col_id in _INDEX_TOGGLEABLE_COLS:
        assert f'<th data-col="{col_id}"' in html, f"th data-col='{col_id}' missing from index header"


@covers(HtmlReporter._render_tree_rows)
def test_index_each_toggleable_column_has_data_col_on_data_cells():
    """Every data cell in a toggleable column must carry its data-col attribute so the JS can find it."""
    summaries = [_make_file_summary("src/a.py", total_stmts=5, total_covered=3, deliberate_covered=2, incidental_covered=1)]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    html = "".join(HtmlReporter()._render_tree_rows(tree, depth=0, parent_id=""))
    for col_id in _INDEX_TOGGLEABLE_COLS:
        assert f'data-col="{col_id}"' in html, f"td data-col='{col_id}' missing from index rows"


@covers(HtmlReporter.render_index_page)
def test_index_col_hidden_matches_python_defaults():
    """True columns must have no col-hidden; False columns must carry col-hidden."""
    html = HtmlReporter().render_index_page("")
    body = html[html.index("<body>"):]
    for col_id, visible in IndexPageReporter.INDEX_COLUMNS.items():
        if visible:
            assert f'data-col="{col_id}" class="col-hidden"' not in body, (
                f"column '{col_id}' is True but has col-hidden"
            )
        else:
            # th uses 'sortable col-hidden'; td (when rows present) uses just 'col-hidden'
            assert (
                f'data-col="{col_id}" class="col-hidden"' in body
                or f'data-col="{col_id}" class="sortable col-hidden"' in body
            ), f"column '{col_id}' is False but missing col-hidden"


@covers(HtmlReporter.render_file_page)
def test_file_page_has_col_controls(tmp_path):
    html = HtmlReporter().render_file_page("src/foo.py", "", "")
    assert 'class="col-controls"' in html


@covers(HtmlReporter.render_file_page)
def test_file_col_controls_has_checkbox_for_every_toggleable_column():
    html = HtmlReporter().render_file_page("src/foo.py", "", "")
    for col_id in _FILE_TOGGLEABLE_COLS:
        assert f'value="{col_id}"' in html, f"checkbox for column '{col_id}' missing from file page"


@covers(HtmlReporter.render_file_page)
def test_file_all_checkboxes_checked_by_default():
    """All column checkboxes on the file page must start checked."""
    import re
    html = HtmlReporter().render_file_page("src/foo.py", "", "")
    checkboxes = re.findall(r'<input[^>]+type="checkbox"[^>]*>', html)
    for cb in checkboxes:
        assert re.search(r'\schecked\s*>', cb), f"checkbox not checked by default: {cb}"


@covers(HtmlReporter.render_file_page)
def test_file_each_toggleable_column_has_data_col_on_header():
    html = HtmlReporter().render_file_page("src/foo.py", "", "")
    for col_id in _FILE_TOGGLEABLE_COLS:
        assert f'<th data-col="{col_id}">' in html, f"th data-col='{col_id}' missing from file page header"


@covers(HtmlReporter.render_line)
def test_file_each_toggleable_column_has_data_col_on_data_cells():
    """Every data cell in a toggleable column must carry its data-col attribute."""
    from coverage_stats.store import LineData
    ld = LineData(incidental_executions=1, deliberate_executions=2,
                  incidental_asserts=3, deliberate_asserts=4,
                  incidental_tests=5, deliberate_tests=6)
    html = HtmlReporter().render_line(1, "x = 1", ld, executable=True)
    for col_id in _FILE_TOGGLEABLE_COLS:
        assert f'data-col="{col_id}"' in html, f"td data-col='{col_id}' missing from line row"


@covers(HtmlReporter.render_file_page)
def test_file_no_col_hidden_class_by_default():
    """No column should be hidden in the static HTML — hiding is applied by JS from localStorage.
    We check only the <body> since the CSS itself contains the .col-hidden rule as text."""
    html = HtmlReporter().render_file_page("src/foo.py", "", "")
    body = html[html.index("<body>"):]
    assert "col-hidden" not in body


@covers(HtmlReporter.render_index_page, HtmlReporter.render_file_page)
def test_col_controls_checkbox_values_match_data_col_attributes():
    """The value of every checkbox must exactly match a data-col attribute in the same page,
    so that the JS toggleCol() function can find the cells to hide/show."""
    import re

    index_html = HtmlReporter().render_index_page("<tr><td>x</td><td data-col='stmts'>1</td></tr>")
    index_cb_values = set(re.findall(r'<input[^>]+type="checkbox"[^>]+value="([^"]+)"', index_html))
    index_data_cols = set(re.findall(r'data-col="([^"]+)"', index_html))
    assert index_cb_values == index_data_cols & index_cb_values, (
        f"index checkbox values {index_cb_values} not all present as data-col: {index_data_cols}"
    )

    file_html = HtmlReporter().render_file_page("f.py", "", "<tr><td>1</td><td></td><td>src</td>"
                                               + "".join(f'<td data-col="{c}">0</td>' for c in _FILE_TOGGLEABLE_COLS)
                                               + "</tr>")
    file_cb_values = set(re.findall(r'<input[^>]+type="checkbox"[^>]+value="([^"]+)"', file_html))
    file_data_cols = set(re.findall(r'data-col="([^"]+)"', file_html))
    assert file_cb_values == file_data_cols & file_cb_values, (
        f"file checkbox values {file_cb_values} not all present as data-col: {file_data_cols}"
    )


# ---------------------------------------------------------------------------
# Python-controlled initial column visibility via INDEX_COLUMNS / FILE_COLUMNS
# ---------------------------------------------------------------------------


@covers(HtmlReporter.render_index_page)
def test_index_column_gets_col_hidden_when_python_config_is_false():
    """Setting INDEX_COLUMNS[col] = False must bake col-hidden into the th and td cells."""
    class _R(IndexPageReporter):
        INDEX_COLUMNS = {**IndexPageReporter.INDEX_COLUMNS, "stmts": False}

    reporter = _R()
    summaries = [_make_file_summary("src/a.py", total_stmts=5, total_covered=3)]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    rows_html = "".join(reporter._render_tree_rows(tree, depth=0, parent_id=""))
    html = reporter.render_index_page(rows_html)
    body = html[html.index("<body>"):]

    assert 'data-col="stmts" class="col-hidden"' in body, "th for stmts should carry col-hidden"
    assert 'data-col="total-pct" class="col-hidden"' not in body, "other cols must not be hidden"

@covers(HtmlReporter.render_index_page)
def test_index_column_gets_col_hidden_when_python_config_is_true():
    """Setting INDEX_COLUMNS[col] = True must NOT add col-hidden to that column's cells."""
    class _R(IndexPageReporter):
        INDEX_COLUMNS = {**IndexPageReporter.INDEX_COLUMNS, "stmts": True}

    reporter = _R()
    summaries = [_make_file_summary("src/a.py", total_stmts=5, total_covered=3)]
    tree = DefaultReportBuilder().build_folder_tree(summaries)
    rows_html = "".join(reporter._render_tree_rows(tree, depth=0, parent_id=""))
    html = reporter.render_index_page(rows_html)
    body = html[html.index("<body>"):]

    # Column is visible: header and data cells render without col-hidden
    assert 'data-col="stmts" class="sortable"' in body, "stmts th must be present and visible"
    assert 'data-col="stmts">5</td>' in body, "stmts td must contain the value without col-hidden"
    assert 'data-col="stmts" class="col-hidden"' not in body, "th for stmts must not carry col-hidden when True"
    assert 'data-col="total-pct" class="col-hidden"' not in body, "other cols must not be hidden"


@covers(HtmlReporter.render_index_page)
def test_index_checkbox_unchecked_when_python_config_is_false():
    """Setting INDEX_COLUMNS[col] = False must render the checkbox without 'checked'."""
    import re

    class _R(IndexPageReporter):
        INDEX_COLUMNS = {**IndexPageReporter.INDEX_COLUMNS, "stmts": False}

    html = _R().render_index_page("")
    stmts_cb = re.search(r'<input[^>]+value="stmts"[^>]*>', html)
    assert stmts_cb, "stmts checkbox not found"
    # Check for 'checked' as a standalone HTML attribute (not inside 'this.checked' in onchange)
    assert not re.search(r'\schecked\s*>', stmts_cb.group(0)), (
        "stmts checkbox must be unchecked when config is False"
    )

    # All other index checkboxes should remain checked
    for col_id in ("total-pct", "delib-pct", "incid-pct"):
        other_cb = re.search(rf'<input[^>]+value="{col_id}"[^>]*>', html)
        assert other_cb and re.search(r'\schecked\s*>', other_cb.group(0)), (
            f"checkbox for '{col_id}' should be checked"
        )


@covers(HtmlReporter.render_file_page)
def test_file_column_gets_col_hidden_when_python_config_is_false():
    """Setting FILE_COLUMNS[col] = False must bake col-hidden into the th and the line td cells."""
    from coverage_stats.store import LineData

    class _R(FilePageReporter):
        FILE_COLUMNS = {**FilePageReporter.FILE_COLUMNS, "inc-exec": False}

    reporter = _R()
    ld = LineData(incidental_executions=1, deliberate_executions=2,
                  incidental_asserts=3, deliberate_asserts=4,
                  incidental_tests=5, deliberate_tests=6)
    line_html = reporter.render_line(1, "x = 1", ld, executable=True)
    html = reporter.render_file_page("f.py", "", line_html)
    body = html[html.index("<body>"):]

    assert 'data-col="inc-exec" class="col-hidden"' in body, "th for inc-exec should carry col-hidden"
    assert 'data-col="inc-exec" class="col-hidden"' in line_html, "td in line row should carry col-hidden"
    assert 'data-col="del-exec" class="col-hidden"' not in body, "other cols must not be hidden"


@covers(HtmlReporter.render_file_page)
def test_file_checkbox_unchecked_when_python_config_is_false():
    """Setting FILE_COLUMNS[col] = False must render the checkbox without 'checked'."""
    import re

    class _R(FilePageReporter):
        FILE_COLUMNS = {**FilePageReporter.FILE_COLUMNS, "inc-exec": False}

    html = _R().render_file_page("f.py", "", "")
    inc_exec_cb = re.search(r'<input[^>]+value="inc-exec"[^>]*>', html)
    assert inc_exec_cb, "inc-exec checkbox not found"
    # Check for 'checked' as a standalone HTML attribute (not inside 'this.checked' in onchange)
    assert not re.search(r'\schecked\s*>', inc_exec_cb.group(0)), (
        "inc-exec checkbox must be unchecked when config is False"
    )

    # All other file checkboxes should remain checked
    for col_id in ("del-exec", "inc-asserts", "del-asserts", "inc-tests", "del-tests"):
        other_cb = re.search(rf'<input[^>]+value="{col_id}"[^>]*>', html)
        assert other_cb and re.search(r'\schecked\s*>', other_cb.group(0)), (
            f"checkbox for '{col_id}' should be checked"
        )


# ---------------------------------------------------------------------------
# File-page cell colour levels (_collect_file_ranges + render_line _ranges)
# ---------------------------------------------------------------------------


def _make_lr(
    lineno: int = 1,
    executable: bool = True,
    ie: int = 0, de: int = 0,
    ia: int = 0, da: int = 0,
    it: int = 0, dt: int = 0,
    partial: bool = False,
) -> LineReport:
    return LineReport(
        lineno=lineno,
        source_text="x = 1",
        executable=executable,
        partial=partial,
        incidental_executions=ie,
        deliberate_executions=de,
        incidental_asserts=ia,
        deliberate_asserts=da,
        incidental_tests=it,
        deliberate_tests=dt,
    )


@covers(FilePageReporter._collect_file_ranges)
def test_collect_file_ranges_finds_max_values():
    lines = [
        _make_lr(ie=3, de=7, ia=1, da=5, it=2, dt=4),
        _make_lr(ie=10, de=2, ia=8, da=3, it=6, dt=9),
    ]
    reporter = FilePageReporter()
    ranges = reporter._collect_file_ranges(lines)
    assert ranges["inc-exec"] == 10
    assert ranges["del-exec"] == 7
    assert ranges["inc-asserts"] == 8
    assert ranges["del-asserts"] == 5
    assert ranges["inc-tests"] == 6
    assert ranges["del-tests"] == 9


@covers(FilePageReporter._collect_file_ranges)
def test_collect_file_ranges_ignores_non_executable_lines():
    """Non-executable lines (comments, blanks) must not influence the range maxima."""
    lines = [
        _make_lr(executable=False, ie=999, de=999, ia=999, da=999, it=999, dt=999),
        _make_lr(executable=True, ie=5, de=5, ia=5, da=5, it=5, dt=5),
    ]
    reporter = FilePageReporter()
    ranges = reporter._collect_file_ranges(lines)
    assert ranges["inc-exec"] == 5
    assert ranges["del-exec"] == 5


@covers(FilePageReporter._collect_file_ranges)
def test_collect_file_ranges_all_non_executable_returns_zeros():
    lines = [_make_lr(executable=False, ie=10, de=10)]
    ranges = FilePageReporter()._collect_file_ranges(lines)
    assert all(v == 0.0 for v in ranges.values())


@covers(HtmlReporter.render_line)
def test_render_line_executable_with_ranges_gets_lvl_class():
    """Executable lines get lvl-N classes on data cells when _ranges is supplied."""
    ld = _make_ld(ie=10, de=10, ia=10, da=10)
    ranges = {
        "inc-exec": 10.0, "del-exec": 10.0,
        "inc-asserts": 10.0, "del-asserts": 10.0,
        "inc-tests": 10.0, "del-tests": 10.0,
    }
    html = HtmlReporter().render_line(1, "x = 1", ld, executable=True, _ranges=ranges)
    # value == max → bucket index 10 → clamped to 9
    assert 'class="lvl-9"' in html


@covers(HtmlReporter.render_line)
def test_render_line_color_level_reflects_bucket():
    """The bucket level should reflect the value's position within the range."""
    ld = _make_ld(ie=5, de=0)
    ranges = {
        "inc-exec": 10.0, "del-exec": 10.0,
        "inc-asserts": 10.0, "del-asserts": 10.0,
        "inc-tests": 10.0, "del-tests": 10.0,
    }
    html = HtmlReporter().render_line(1, "x = 1", ld, executable=True, _ranges=ranges)
    # 5 / 10 * 10 = 5 → lvl-5
    assert 'data-col="inc-exec" class="lvl-5"' in html
    # 0 / 10 * 10 = 0 → lvl-0
    assert 'data-col="del-exec" class="lvl-0"' in html


@covers(HtmlReporter.render_line)
def test_render_line_non_executable_with_ranges_no_lvl_class():
    """Non-executable lines must never receive colour level classes."""
    ld = _make_ld(ie=10, de=10)
    ranges = {
        "inc-exec": 10.0, "del-exec": 10.0,
        "inc-asserts": 10.0, "del-asserts": 10.0,
        "inc-tests": 10.0, "del-tests": 10.0,
    }
    html = HtmlReporter().render_line(1, "# comment", ld, executable=False, _ranges=ranges)
    assert "lvl-" not in html
    assert 'class=' not in html


@covers(HtmlReporter.render_line)
def test_render_line_without_ranges_no_lvl_class():
    """Without _ranges, no colour level classes are added (backward-compatible default)."""
    ld = _make_ld(ie=5, de=3, ia=2, da=1)
    html = HtmlReporter().render_line(1, "x = 1", ld, executable=True)
    assert "lvl-" not in html


@covers(HtmlReporter.render_line)
def test_render_line_missed_executable_with_ranges_gets_lvl_0():
    """Missed executable lines (all zeros) get lvl-0 on every data cell."""
    ranges = {
        "inc-exec": 10.0, "del-exec": 10.0,
        "inc-asserts": 10.0, "del-asserts": 10.0,
        "inc-tests": 10.0, "del-tests": 10.0,
    }
    html = HtmlReporter().render_line(1, "x = 1", None, executable=True, _ranges=ranges)
    assert 'class="missed"' in html
    # Every data cell should be lvl-0 (0 / max = 0)
    assert html.count('class="lvl-0"') == 6


@covers(FilePageReporter._write_file_page)
def test_write_html_file_page_contains_color_classes(tmp_path):
    """write() must produce file pages with lvl-N classes when lines have non-zero values."""
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    # Two lines with different incidental execution counts so bucketing produces both lvl-0 and lvl-9
    store.get_or_create((str(rootdir / "mod.py"), 1)).incidental_executions = 1
    store.get_or_create((str(rootdir / "mod.py"), 2)).incidental_executions = 10
    config = make_config(rootdir)
    report = DefaultReportBuilder().build(store, config)

    out_dir = tmp_path / "out"
    HtmlReporter().write(report,out_dir)

    file_html = (out_dir / "mod.py.html").read_text()
    assert "lvl-" in file_html
