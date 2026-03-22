from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from coverage_stats import covers
from coverage_stats.store import SessionStore
from coverage_stats.reporters.json_reporter import write_json
from coverage_stats.reporters.report_data import build_report


def make_config(rootdir: Path) -> SimpleNamespace:
    return SimpleNamespace(rootpath=rootdir)


@covers(write_json)
def test_empty_store_produces_empty_files(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    report = build_report(store, config)
    write_json(report, tmp_path / "out")
    result = json.loads((tmp_path / "out" / "coverage-stats.json").read_text())
    assert result == {"files": {}}


@covers(write_json)
def test_single_file_multi_line_structure(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1
    store.get_or_create((abs_file, 3)).deliberate_executions = 2

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_json(report, out_dir)

    result = json.loads((out_dir / "coverage-stats.json").read_text())
    assert "src/foo.py" in result["files"]
    file_data = result["files"]["src/foo.py"]
    assert "1" in file_data["lines"]
    assert "3" in file_data["lines"]
    assert file_data["lines"]["1"]["incidental_executions"] == 1
    assert file_data["lines"]["3"]["deliberate_executions"] == 2


@covers(write_json)
def test_summary_calculations(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    # 2 lines: line 1 has deliberate_executions=5, line 2 has none
    store.get_or_create((abs_file, 1)).deliberate_executions = 5
    store.get_or_create((abs_file, 2))  # no executions

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    src = rootdir / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "foo.py").write_text("x = 1\ny = 2\n")
    report = build_report(store, config)
    write_json(report, out_dir)

    result = json.loads((out_dir / "coverage-stats.json").read_text())
    summary = result["files"]["src/foo.py"]["summary"]
    assert summary["total_stmts"] == 2
    assert summary["deliberate_coverage_pct"] == 50.0
    assert summary["incidental_coverage_pct"] == 0.0


@covers(write_json)
def test_assert_density_calculation(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "bar.py")
    ld1 = store.get_or_create((abs_file, 1))
    ld1.incidental_asserts = 4
    ld1.deliberate_asserts = 2
    ld1.incidental_executions = 1
    store.get_or_create((abs_file, 2))  # no asserts

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    src = rootdir / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "bar.py").write_text("x = 1\ny = 2\n")
    report = build_report(store, config)
    write_json(report, out_dir)

    result = json.loads((out_dir / "coverage-stats.json").read_text())
    summary = result["files"]["src/bar.py"]["summary"]
    assert summary["incidental_assert_density"] == 4 / 2
    assert summary["deliberate_assert_density"] == 2 / 2


@covers(write_json)
def test_path_outside_rootdir_fallback(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    # abs_path is outside rootdir
    outside_file = str(tmp_path / "other" / "baz.py")
    store.get_or_create((outside_file, 10)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_json(report, out_dir)

    result = json.loads((out_dir / "coverage-stats.json").read_text())
    # key should be the POSIX absolute path, not relative
    expected_key = Path(outside_file).as_posix()
    assert expected_key in result["files"]


@covers(write_json)
def test_lineno_keys_are_strings(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "mod.py")
    store.get_or_create((abs_file, 42)).incidental_executions = 3

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_json(report, out_dir)

    result = json.loads((out_dir / "coverage-stats.json").read_text())
    file_lines = result["files"]["mod.py"]["lines"]
    assert "42" in file_lines
    # JSON keys are always strings; verify the integer key is NOT present
    assert 42 not in file_lines


@covers(write_json)
def test_partial_line_flag_present(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    src_file = rootdir / "mod.py"
    src_file.write_text("if x:\n    pass\n")
    store.get_or_create((str(src_file), 1)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_json(report, out_dir)

    result = json.loads((out_dir / "coverage-stats.json").read_text())
    line = result["files"]["mod.py"]["lines"]["1"]
    assert "partial" in line


@covers(write_json)
def test_non_partial_line_flag_is_false(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "mod.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_json(report, out_dir)

    result = json.loads((out_dir / "coverage-stats.json").read_text())
    line = result["files"]["mod.py"]["lines"]["1"]
    assert line["partial"] is False


@covers(write_json)
def test_output_dir_created_if_missing(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    out_dir = tmp_path / "nested" / "deep" / "out"
    assert not out_dir.exists()
    report = build_report(store, config)
    write_json(report, out_dir)
    assert (out_dir / "coverage-stats.json").exists()
