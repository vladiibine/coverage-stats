from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from coverage_stats.store import SessionStore
from coverage_stats.reporters.html import (
    write_html,
    render_line,
    render_file_row,
    render_folder_section,
    render_index_page,
    render_file_page,
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


def test_index_contains_details_element(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1
    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    write_html(store, config, out_dir)
    content = (out_dir / "index.html").read_text()
    assert "<details" in content


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


def test_multiple_folders_creates_multiple_details(tmp_path):
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
    assert content.count("<details") == 2


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
    result = render_line(1, "x = 1", ld)
    assert 'class="deliberate"' in result
    assert "<td>1</td>" in result


def test_render_line_incidental_class():
    ld = _make_ld(ie=2)
    result = render_line(7, "pass", ld)
    assert 'class="incidental"' in result


def test_render_line_no_class():
    ld = _make_ld()
    result = render_line(3, "import os", ld)
    assert 'class=' not in result
    assert "<tr>" in result


def test_render_line_escapes_html():
    ld = _make_ld()
    result = render_line(1, "<script>alert(1)</script>", ld)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_render_file_row_contains_link():
    ld = _make_ld(de=1)
    lines = {1: ld, 2: _make_ld()}
    result = render_file_row("src/foo.py", lines, "src__foo.py.html")
    assert 'href="src__foo.py.html"' in result
    assert "src/foo.py" in result


def test_render_file_row_pct_calculation():
    lines = {1: _make_ld(de=1), 2: _make_ld(), 3: _make_ld()}
    result = render_file_row("x.py", lines, "x.py.html")
    # 1/3 deliberate = 33.3%
    assert "33.3%" in result


def test_render_folder_section_contains_details():
    result = render_folder_section("src", "<tr><td>row</td></tr>")
    assert "<details" in result
    assert "<summary>src</summary>" in result
    assert "row" in result


def test_render_index_page_full_html():
    result = render_index_page("<details>sec</details>")
    assert "<!DOCTYPE html>" in result
    assert "<style>" in result
    assert "<details>sec</details>" in result


def test_render_file_page_full_html():
    result = render_file_page("src/foo.py", "<tr><td>42</td></tr>")
    assert "<!DOCTYPE html>" in result
    assert "src/foo.py" in result
    assert "42" in result
    assert "<style>" in result
