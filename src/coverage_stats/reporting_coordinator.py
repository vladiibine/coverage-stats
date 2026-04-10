from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pytest

if TYPE_CHECKING:
    from coverage_stats.plugin import CoverageStatsCustomization
    from coverage_stats.store import SessionStore


class _XdistWorkerNode(Protocol):
    workeroutput: dict[str, str]


class ReportingCoordinator:
    """Manages report writing and xdist worker store merging.

    Registered on xdist controllers and single-process runs; NOT registered on
    xdist workers (which only trace and serialize).  Owns the report-writing
    pipeline and the merge of per-worker stores into the controller store.
    """

    def __init__(
        self,
        store: SessionStore,
        customization: CoverageStatsCustomization,
        *,
        coverage_py_active: bool = False,
    ) -> None:
        self._enabled: bool = True
        self._coverage_py_active = coverage_py_active
        self._store = store
        self._customization = customization

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node: _XdistWorkerNode, error: BaseException | None) -> None:
        """Merge coverage data from an xdist worker into the controller's store."""
        if not self._enabled:
            return
        raw = getattr(node, "workeroutput", {}).get("coverage_stats_data")
        if raw:
            assert self._store is not None
            try:
                worker_store = type(self._store).from_dict(json.loads(raw))
            except Exception as exc:
                warnings.warn(f"coverage-stats: failed to deserialise worker store: {exc}")
                return
            self._store.merge(worker_store)

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
        """Inject into coverage.py (fallback) and write all configured reports.

        tryfirst=True ensures we run before pytest-cov's pytest_sessionfinish so
        that any data we inject into coverage.py's CoverageData object is present
        before coverage.py calls cov.save() and generates its report.
        """
        if not self._enabled:
            return
        config = session.config
        # Best-effort fallback injection for coverage tool integrations that call
        # cov.save() from pytest_sessionfinish (older pytest-cov versions, custom
        # runners).  The primary injection path is patch_coverage_save() called in
        # TracingCoordinator.pytest_collection_finish.
        if self._coverage_py_active and sys.version_info < (3, 12):
            self._customization.get_coverage_py_interop().inject_into_coverage_py(self._store)
        fmt_str = config.getoption("--coverage-stats-format") or config.getini("coverage_stats_format")
        formats = [f.strip() for f in (fmt_str or "").split(",") if f.strip()]
        out_str = config.getoption("--coverage-stats-output") or config.getini("coverage_stats_output_dir")
        output_dir = Path(out_str).resolve()
        reporter_str = config.getoption("--coverage-stats-reporter") or config.getini("coverage_stats_reporters")
        reporter_paths = [r.strip() for r in (reporter_str or "").split(",") if r.strip()]

        reporters = self._customization.get_reporters(formats, reporter_paths)
        report = self._customization.get_report_builder().build(self._store, config)
        for name, reporter in reporters:
            try:
                reporter.write(report, output_dir)
            except Exception as exc:
                warnings.warn(f"coverage-stats: reporter {name!r} failed: {exc}")
