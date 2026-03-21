from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from coverage_stats.store import SessionStore
from coverage_stats.reporters.html import (
    write_html,
    render_line,
    render_index_page,
    render_file_page,
    render_file_stats,
    _FileEntry,
    _build_file_tree,
    _render_tree_rows,
)


def make_config(rootdir: Path) -> SimpleNamespace:
    return SimpleNamespace(rootpath=rootdir)


# ---------------------------------------------------------------------------
# write_html integration tests
# ---------------------------------------------------------------------------


def test_empty_store_writes_index(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    write_html(store, config, tmp_path / "out")
    assert (tmp_path / "out" / "index.html").exists()


def test_empty_store_no_per_file_pages(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    out_dir = tmp_path / "out"
    write_html(store, config, out_dir)
    html_files = list(out_dir.glob("*.html"))
    assert html_files == [out_dir / "index.html"]


def test_single_file_writes_per_file_page(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    write_html(store, config, out_dir)
    assert (out_dir / "src__foo.py.html").exists()


def test_index_contains_table_and_folder_row(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    write_html(store, config, out_dir)
    content = (out_dir / "index.html").read_text()
    assert "<table>" in content
    assert "folder-row" in content


def test_index_contains_folder_name(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    write_html(store, config, out_dir)
    content = (out_dir / "index.html").read_text()
    assert "src" in content


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
    write_html(store, config, out_dir)
    content = (out_dir / "index.html").read_text()
    assert content.count("<table>") == 1  # single table
    assert content.count('class="folder-row"') == 2  # one row per top-level folder


def test_per_file_page_contains_lineno(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "mod.py")
    store.get_or_create((abs_file, 42)).incidental_executions = 3
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    write_html(store, config, out_dir)
    content = (out_dir / "mod.py.html").read_text()
    assert "42" in content


def test_deliberate_line_gets_green_class(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "mod.py")
    store.get_or_create((abs_file, 5)).deliberate_executions = 2
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    write_html(store, config, out_dir)
    content = (out_dir / "mod.py.html").read_text()
    assert "deliberate" in content


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
    write_html(store, config, out_dir)
    content = (out_dir / "mod.py.html").read_text()
    assert "incidental" in content


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
    write_html(store, config, out_dir)
    content = (out_dir / "mod.py.html").read_text()

    # Every line number 1-5 must appear
    for lineno in range(1, 6):
        assert f"<td>{lineno}</td>" in content, f"Line {lineno} missing from file page"


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
    write_html(store, config, out_dir)
    content = (out_dir / "mod.py.html").read_text()

    assert "uncovered_line" in content


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
    write_html(store, config, out_dir)
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
    write_html(store, config, out_dir)
    content = (out_dir / "index.html").read_text()

    # The index must show 10 (total executable stmts), not 2 (tracked stmts)
    assert "<td>10</td>" in content
    assert "<td>2</td>" not in content


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
    write_html(store, config, out_dir)
    content = (out_dir / "index.html").read_text()

    import re
    # The file row renders as: <a href="...">__init__.py</a></td><td>{stmts}</td>
    # Match the stmt count cell that immediately follows the __init__.py link.
    match = re.search(r'__init__\.py</a></td><td>(\d+)</td>', content)
    assert match is not None, "__init__.py row not found in index"
    assert match.group(1) == "0", f"expected 0 stmts for empty __init__.py, got {match.group(1)}"


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
    write_html(store, config, out_dir)
    content = (out_dir / "index.html").read_text()

    # Falls back to len(lines) = 2
    assert "<td>2</td>" in content


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
    write_html(store, config, out_dir)
    assert (out_dir / "nonexistent.py.html").exists()
    content = (out_dir / "nonexistent.py.html").read_text()
    assert "1" in content


def test_path_outside_rootdir_fallback(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    outside_file = str(tmp_path / "other" / "baz.py")
    store.get_or_create((outside_file, 10)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    write_html(store, config, out_dir)
    # index.html should exist and contain the absolute path
    content = (out_dir / "index.html").read_text()
    assert "baz.py" in content


def test_output_dir_created_if_missing(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    out_dir = tmp_path / "nested" / "deep" / "out"
    assert not out_dir.exists()
    write_html(store, config, out_dir)
    assert (out_dir / "index.html").exists()


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


def test_render_line_deliberate_class():
    ld = _make_ld(de=1)
    result = render_line(1, "x = 1", ld, executable=True)
    assert 'class="deliberate"' in result
    assert "<td>1</td>" in result


def test_render_line_incidental_class():
    ld = _make_ld(ie=2)
    result = render_line(7, "pass", ld, executable=True)
    assert 'class="incidental"' in result


def test_render_line_missed_executable_gets_missed_class():
    ld = _make_ld()
    result = render_line(3, "import os", ld, executable=True)
    assert 'class="missed"' in result


def test_render_line_non_executable_no_class():
    ld = _make_ld(de=1)
    result = render_line(3, "# comment", ld, executable=False)
    assert 'class=' not in result
    assert "<tr>" in result


def test_render_line_missed_class():
    result = render_line(5, "x = 1", None, executable=True)
    assert 'class="missed"' in result


def test_render_line_escapes_html():
    ld = _make_ld()
    result = render_line(1, "<script>alert(1)</script>", ld, executable=True)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_build_file_tree_groups_by_folder():
    entries = [
        _FileEntry("src/a.py", "src__a.py.html", 10, 7, 0, 0, 0, 0, 5, 3),
        _FileEntry("src/sub/b.py", "src__sub__b.py.html", 8, 5, 0, 0, 0, 0, 2, 4),
    ]
    tree = _build_file_tree(entries)
    assert "src" in tree.subfolders
    src_node = tree.subfolders["src"]
    assert len(src_node.files) == 1
    assert src_node.files[0].rel_path == "src/a.py"
    assert "sub" in src_node.subfolders
    assert src_node.subfolders["sub"].files[0].rel_path == "src/sub/b.py"


def test_folder_node_aggregates_stats():
    entries = [
        _FileEntry("src/a.py", "src__a.py.html", 10, 7, 4, 3, 2, 1, 5, 3),
        _FileEntry("src/sub/b.py", "src__sub__b.py.html", 8, 5, 2, 1, 1, 0, 2, 4),
    ]
    tree = _build_file_tree(entries)
    src = tree.subfolders["src"]
    assert src.agg_total_stmts() == 18
    assert src.agg_total_covered() == 12
    assert src.agg_deliberate() == 7
    assert src.agg_incidental() == 7
    assert src.agg_arcs_total() == 6
    assert src.agg_arcs_covered() == 4
    assert src.agg_arcs_deliberate() == 3
    assert src.agg_arcs_incidental() == 1


def test_render_tree_rows_contains_link_and_folder():
    entries = [
        _FileEntry("src/foo.py", "src__foo.py.html", 3, 2, 0, 0, 0, 0, 1, 2),
    ]
    tree = _build_file_tree(entries)
    html = "".join(_render_tree_rows(tree, depth=0, parent_id=""))
    assert 'href="src__foo.py.html"' in html
    assert "foo.py" in html
    assert "src/" in html  # folder row


def test_render_tree_rows_pct_calculation():
    entries = [
        _FileEntry("src/x.py", "src__x.py.html", 3, 2, 0, 0, 0, 0, 1, 0),
    ]
    tree = _build_file_tree(entries)
    html = "".join(_render_tree_rows(tree, depth=0, parent_id=""))
    assert "33.3%" in html  # 1/3 deliberate on file row
    assert "66.7%" in html  # 2/3 total on file row


def test_render_index_page_full_html():
    result = render_index_page("<tr><td>row</td></tr>")
    assert "<!DOCTYPE html>" in result
    assert "<style>" in result
    assert "<script>" in result
    assert "<tr><td>row</td></tr>" in result
    assert "<table>" in result


def test_render_file_page_full_html():
    result = render_file_page("src/foo.py", "<div>stats</div>", "<tr><td>42</td></tr>")
    assert "<!DOCTYPE html>" in result
    assert "src/foo.py" in result
    assert "42" in result
    assert "stats" in result
    assert "<style>" in result


def test_render_file_stats_shows_total_pct():
    result = render_file_stats(
        total_stmts=10, covered=7, total_pct=70.0,
        deliberate_cnt=4, deliberate_pct=40.0,
        incidental_cnt=3, incidental_pct=30.0,
    )
    assert "70.0%" in result
    assert "total %" in result


def test_folder_node_agg_total_covered():
    entries = [
        _FileEntry("a/x.py", "a__x.py.html", 10, 8, 0, 0, 0, 0, 6, 3),
        _FileEntry("a/y.py", "a__y.py.html", 5, 3, 0, 0, 0, 0, 1, 2),
    ]
    tree = _build_file_tree(entries)
    node = tree.subfolders["a"]
    assert node.agg_total_covered() == 11  # 8 + 3


def test_render_tree_rows_total_pct_column():
    entries = [
        _FileEntry("src/z.py", "src__z.py.html", 4, 3, 0, 0, 0, 0, 2, 1),
    ]
    tree = _build_file_tree(entries)
    html = "".join(_render_tree_rows(tree, depth=0, parent_id=""))
    assert "75.0%" in html   # 3/4 total on file row
    assert "50.0%" in html   # 2/4 deliberate on file row


def test_index_page_has_total_pct_header():
    result = render_index_page("")
    assert "Total %" in result
