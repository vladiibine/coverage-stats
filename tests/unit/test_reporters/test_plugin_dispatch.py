from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from coverage_stats.store import SessionStore
from coverage_stats.plugin import CoverageStatsCustomization
from coverage_stats.reporting_coordinator import ReportingCoordinator


def _make_stub_config() -> SimpleNamespace:
    return SimpleNamespace(
        pluginmanager=SimpleNamespace(hasplugin=lambda name: False),
        getoption=lambda name, default=None: default,
        getini=lambda name: {"coverage_stats_precision": "1"}.get(name, ""),
    )


def make_config(rootdir: Path, fmt: str, out_dir: str) -> SimpleNamespace:
    return SimpleNamespace(
        rootpath=rootdir,
        getoption=lambda opt, **kw: {
            "--coverage-stats-format": fmt,
            "--coverage-stats-output": str(out_dir),
            "--coverage-stats-reporter": None,
        }.get(opt),
        getini=lambda key: {
            "coverage_stats_format": "",
            "coverage_stats_output_dir": "coverage-stats-report",
            "coverage_stats_reporters": "",
        }.get(key, ""),
    )


def make_reporting_coordinator(store: SessionStore) -> ReportingCoordinator:
    return ReportingCoordinator(store, CoverageStatsCustomization(_make_stub_config()))


def test_sessionfinish_json_and_csv_both_written(tmp_path):
    """AC-4: --coverage-stats-format=json,csv writes both output files."""
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    out_dir = tmp_path / "out"

    config = make_config(rootdir, fmt="json,csv", out_dir=str(out_dir))
    session = SimpleNamespace(config=config)

    coord = make_reporting_coordinator(store)
    coord.pytest_sessionfinish(session=session, exitstatus=0)

    assert (out_dir / "coverage-stats.json").exists()
    assert (out_dir / "coverage-stats.csv").exists()


def test_sessionfinish_html_format_no_error_no_file(tmp_path):
    """AC-5: --coverage-stats-format=html writes index.html, no coverage-stats.html, no error."""
    store = SessionStore()
    rootdir = tmp_path / "project"
    rootdir.mkdir()
    out_dir = tmp_path / "out"

    config = make_config(rootdir, fmt="html", out_dir=str(out_dir))
    session = SimpleNamespace(config=config)

    coord = make_reporting_coordinator(store)
    coord.pytest_sessionfinish(session=session, exitstatus=0)  # must not raise

    # HTML report uses index.html, not coverage-stats.html
    assert not (out_dir / "coverage-stats.html").exists()
    assert (out_dir / "index.html").exists()
