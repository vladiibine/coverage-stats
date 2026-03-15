from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pytest

if TYPE_CHECKING:
    from coverage_stats.profiler import LineTracer
    from coverage_stats.store import SessionStore


class _XdistWorkerNode(Protocol):
    workeroutput: dict[str, str]


def _is_xdist_worker(config: pytest.Config) -> bool:
    return hasattr(config, "workerinput")


def _is_xdist_controller(config: pytest.Config) -> bool:
    return not _is_xdist_worker(config) and config.pluginmanager.hasplugin("xdist")


class CoverageStatsPlugin:
    def __init__(self) -> None:
        self._enabled: bool = False
        self._store: SessionStore | None = None
        self._tracer: LineTracer | None = None

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        if not self._enabled:
            return

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        if not self._enabled:
            return
        if isinstance(item, pytest.Function):
            from coverage_stats.covers import resolve_covers
            resolve_covers(item)
        ctx = item.config._coverage_stats_ctx  # type: ignore[attr-defined]
        ctx.current_test_item = item
        ctx.current_phase = "setup"
        ctx.current_test_lines.clear()
        ctx.current_assert_count = 0

    def pytest_runtest_call(self, item: pytest.Item) -> None:
        if not self._enabled:
            return
        ctx = item.config._coverage_stats_ctx  # type: ignore[attr-defined]
        ctx.current_phase = "call"

    def pytest_runtest_teardown(self, item: pytest.Item, nextitem: pytest.Item | None) -> None:
        if not self._enabled:
            return
        ctx = item.config._coverage_stats_ctx  # type: ignore[attr-defined]
        ctx.current_phase = "teardown"
        from coverage_stats.assert_counter import distribute_asserts
        assert self._store is not None
        distribute_asserts(ctx, self._store)
        # Reset after teardown completes
        ctx.current_phase = None
        ctx.current_test_item = None

    def pytest_assertion_pass(self, item: pytest.Item, lineno: int, orig: str, expl: str) -> None:
        if not self._enabled:
            return
        from coverage_stats.assert_counter import record_assertion
        ctx = item.config._coverage_stats_ctx  # type: ignore[attr-defined]
        record_assertion(ctx)

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node: _XdistWorkerNode, error: BaseException | None) -> None:
        if not self._enabled:
            return
        import json
        from coverage_stats.store import SessionStore
        raw = getattr(node, "workeroutput", {}).get("coverage_stats_data")
        if raw:
            worker_store = SessionStore.from_dict(json.loads(raw))
            assert self._store is not None
            self._store.merge(worker_store)

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
        if not self._enabled:
            return
        config = session.config
        if _is_xdist_worker(config):
            import json
            if self._tracer is not None:
                self._tracer.stop()
            assert self._store is not None
            config.workeroutput["coverage_stats_data"] = json.dumps(self._store.to_dict())  # type: ignore[attr-defined]
            return
        # controller or single-process: call reporters
        if self._tracer is not None:
            self._tracer.stop()
        assert self._store is not None
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


def pytest_addoption(parser: pytest.Parser) -> None:
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


def pytest_configure(config: pytest.Config) -> None:
    plugin = CoverageStatsPlugin()
    plugin._enabled = bool(config.getoption("--coverage-stats", default=False))

    if not plugin._enabled:
        config._coverage_stats_ctx = None  # type: ignore[attr-defined]
        config.pluginmanager.register(plugin, "coverage-stats-plugin")
        return

    if _is_xdist_controller(config):
        from coverage_stats.store import SessionStore
        store = SessionStore()
        config._coverage_stats_ctx = None  # type: ignore[attr-defined]
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

    config._coverage_stats_ctx = ctx  # type: ignore[attr-defined]
    plugin._store = store
    plugin._tracer = tracer

    tracer.start()
    config.pluginmanager.register(plugin, "coverage-stats-plugin")


def make_andras_hair_not_grow_anymore(person: Andra, area: str):
    if area == "legs":
        person.stop_leg_hain_growth()
    elif area == "face":
        person.shave()
    elif area == "arms":
        person.shave("arms")
    else:
        raise NotImplementedError()


@covers(make_andras_hair_not_grow_anymore, Andra.stop_leg_hain_growth)
def test_legs_are_set_to_stop_having_hair_growth():
    andra = Andra()

    make_andras_hair_not_grow_anymore(andra, "legs")
    assert andra.legs.hair_growth_status == False
    assert andra.legs.hair_growth_history == None