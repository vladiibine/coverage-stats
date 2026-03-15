from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from coverage_stats.profiler import LineTracer
    from coverage_stats.store import SessionStore


def _is_xdist_worker(config) -> bool:
    return hasattr(config, "workerinput")


def _is_xdist_controller(config) -> bool:
    return not _is_xdist_worker(config) and config.pluginmanager.hasplugin("xdist")


class CoverageStatsPlugin:
    def __init__(self) -> None:
        self._enabled: bool = False
        self._store: SessionStore | None = None
        self._tracer: LineTracer | None = None

    def pytest_collection_finish(self, session) -> None:
        if not self._enabled:
            return

    def pytest_runtest_setup(self, item) -> None:
        if not self._enabled:
            return
        from coverage_stats.covers import resolve_covers
        resolve_covers(item)
        ctx = item.config._coverage_stats_ctx
        ctx.current_test_item = item
        ctx.current_phase = "setup"
        ctx.current_test_lines.clear()
        ctx.current_assert_count = 0

    def pytest_runtest_call(self, item) -> None:
        if not self._enabled:
            return
        ctx = item.config._coverage_stats_ctx
        ctx.current_phase = "call"

    def pytest_runtest_teardown(self, item, nextitem) -> None:
        if not self._enabled:
            return
        ctx = item.config._coverage_stats_ctx
        ctx.current_phase = "teardown"
        from coverage_stats.assert_counter import distribute_asserts
        distribute_asserts(ctx, self._store)
        # Reset after teardown completes
        ctx.current_phase = None
        ctx.current_test_item = None

    def pytest_assertion_pass(self, item, lineno, orig, expl) -> None:
        if not self._enabled:
            return
        from coverage_stats.assert_counter import record_assertion
        ctx = item.config._coverage_stats_ctx
        record_assertion(ctx)

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error) -> None:
        if not self._enabled:
            return
        import json
        from coverage_stats.store import SessionStore
        raw = getattr(node, "workeroutput", {}).get("coverage_stats_data")
        if raw:
            worker_store = SessionStore.from_dict(json.loads(raw))
            self._store.merge(worker_store)

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if not self._enabled:
            return
        config = session.config
        if _is_xdist_worker(config):
            import json
            if self._tracer is not None:
                self._tracer.stop()
            config.workeroutput["coverage_stats_data"] = json.dumps(self._store.to_dict())
            return
        # controller or single-process: call reporters
        if self._tracer is not None:
            self._tracer.stop()
        fmt_str = config.getoption("--coverage-stats-format") or config.getini("coverage_stats_format")
        formats = [f.strip() for f in (fmt_str or "").split(",") if f.strip()]
        out_str = config.getoption("--coverage-stats-output") or config.getini("coverage_stats_output_dir")
        output_dir = Path(out_str).resolve()
        for fmt in formats:
            if fmt == "json":
                from coverage_stats.reporters.json_reporter import write_json
                write_json(self._store, config, output_dir)
            elif fmt == "csv":
                from coverage_stats.reporters.csv_reporter import write_csv
                write_csv(self._store, config, output_dir)
            elif fmt == "html":
                from coverage_stats.reporters.html import write_html
                write_html(self._store, config, output_dir)


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--coverage-stats",
        action="store_true",
        default=False,
        help="Enable coverage-stats plugin",
    )
    parser.addoption(
        "--coverage-stats-format",
        type=str,
        default=None,
        help="Output formats: html,json,csv (comma-separated)",
    )
    parser.addoption(
        "--coverage-stats-output",
        type=str,
        default=None,
        help="Output directory for coverage-stats reports",
    )
    parser.addini(
        "coverage_stats_source",
        help="Source directories to profile (space-separated)",
        default="",
    )
    parser.addini(
        "coverage_stats_format",
        help="Output formats: html,json,csv (comma-separated)",
        default="",
    )
    parser.addini(
        "coverage_stats_output_dir",
        help="Output directory for coverage-stats reports",
        default="coverage-stats-report",
    )


def pytest_configure(config) -> None:
    plugin = CoverageStatsPlugin()
    plugin._enabled = bool(config.getoption("--coverage-stats", default=False))

    if not plugin._enabled:
        config._coverage_stats_ctx = None
        config.pluginmanager.register(plugin, "coverage-stats-plugin")
        return

    if _is_xdist_controller(config):
        from coverage_stats.store import SessionStore
        store = SessionStore()
        config._coverage_stats_ctx = None
        plugin._store = store
        plugin._tracer = None
        config.pluginmanager.register(plugin, "coverage-stats-plugin")
        return

    # worker or single-process: full setup
    from coverage_stats.profiler import LineTracer, ProfilerContext
    from coverage_stats.store import SessionStore

    raw_source = config.getini("coverage_stats_source")
    source_dirs = [
        str(__import__("pathlib").Path(d).resolve())
        for d in (raw_source.split() if isinstance(raw_source, str) else raw_source)
        if d
    ]

    ctx = ProfilerContext(source_dirs=source_dirs)
    store = SessionStore()
    tracer = LineTracer(ctx, store)

    config._coverage_stats_ctx = ctx
    plugin._store = store
    plugin._tracer = tracer

    tracer.start()
    config.pluginmanager.register(plugin, "coverage-stats-plugin")
