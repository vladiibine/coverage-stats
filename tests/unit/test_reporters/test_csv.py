from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

from coverage_stats import covers
from coverage_stats.store import SessionStore
from coverage_stats.reporters.csv_reporter import write_csv
from coverage_stats.reporters.report_data import build_report


def make_config(rootdir: Path) -> SimpleNamespace:
    return SimpleNamespace(rootpath=rootdir)


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


@covers(write_csv)
def test_empty_store_writes_header_only(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_csv(report, out_dir)

    rows = read_csv_rows(out_dir / "coverage-stats.csv")
    assert len(rows) == 1
    assert rows[0] == ["file", "lineno", "incidental_executions", "deliberate_executions", "incidental_asserts", "deliberate_asserts", "incidental_tests", "deliberate_tests", "partial"]


@covers(write_csv)
def test_correct_column_order(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "src" / "foo.py")
    ld = store.get_or_create((abs_file, 5))
    ld.incidental_executions = 1
    ld.deliberate_executions = 2
    ld.incidental_asserts = 3
    ld.deliberate_asserts = 4

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_csv(report, out_dir)

    rows = read_csv_rows(out_dir / "coverage-stats.csv")
    assert rows[0] == ["file", "lineno", "incidental_executions", "deliberate_executions", "incidental_asserts", "deliberate_asserts", "incidental_tests", "deliberate_tests", "partial"]
    assert rows[1] == ["src/foo.py", "5", "1", "2", "3", "4", "0", "0", "False"]


@covers(write_csv)
def test_rows_sorted_by_file_then_lineno(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()

    file_a = str(rootdir / "a.py")
    file_b = str(rootdir / "b.py")

    store.get_or_create((file_b, 1)).incidental_executions = 1
    store.get_or_create((file_a, 10)).incidental_executions = 1
    store.get_or_create((file_a, 2)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_csv(report, out_dir)

    rows = read_csv_rows(out_dir / "coverage-stats.csv")
    data_rows = rows[1:]
    files = [r[0] for r in data_rows]
    linenos = [int(r[1]) for r in data_rows]

    assert files == ["a.py", "a.py", "b.py"]
    assert linenos == [2, 10, 1]


@covers(write_csv)
def test_path_outside_rootdir_fallback(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    outside_file = str(tmp_path / "other" / "baz.py")
    store.get_or_create((outside_file, 7)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_csv(report, out_dir)

    rows = read_csv_rows(out_dir / "coverage-stats.csv")
    assert len(rows) == 2
    expected_file_key = Path(outside_file).as_posix()
    assert rows[1][0] == expected_file_key


@covers(write_csv)
def test_partial_column_false_for_non_branching_line(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    abs_file = str(rootdir / "mod.py")
    store.get_or_create((abs_file, 1)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_csv(report, out_dir)

    rows = read_csv_rows(out_dir / "coverage-stats.csv")
    assert rows[1][-1] == "False"


@covers(write_csv)
def test_partial_column_true_for_partial_branch(tmp_path):
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    src_file = rootdir / "mod.py"
    src_file.write_text("if x:\n    pass\n")
    store.get_or_create((str(src_file), 1)).incidental_executions = 1

    config = make_config(rootdir)
    out_dir = tmp_path / "out"
    report = build_report(store, config)
    write_csv(report, out_dir)

    rows = read_csv_rows(out_dir / "coverage-stats.csv")
    line1 = next(r for r in rows[1:] if r[1] == "1")
    assert line1[-1] == "True"


@covers(write_csv)
def test_output_dir_created_if_missing(tmp_path):
    store = SessionStore()
    config = make_config(tmp_path)
    out_dir = tmp_path / "nested" / "deep" / "out"
    assert not out_dir.exists()
    report = build_report(store, config)
    write_csv(report, out_dir)
    assert (out_dir / "coverage-stats.csv").exists()
