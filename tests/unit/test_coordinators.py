"""Unit tests for TracingCoordinator and ReportingCoordinator.

All tests use lightweight stubs instead of pytester so they run in
milliseconds.  The pytest_runtest_setup branch that calls resolve_covers only
for pytest.Function items is exercised here via a minimal FakeFunction;
end-to-end wiring is verified by the integration tests.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from coverage_stats import covers
from coverage_stats.plugin import CoverageStatsCustomization
from coverage_stats.profiler import ProfilerContext
from coverage_stats.reporting_coordinator import ReportingCoordinator
from coverage_stats.store import SessionStore
from coverage_stats.tracing_coordinator import TracingCoordinator


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubTracer:
    """Records start/stop calls; does not touch sys.settrace."""

    def __init__(self) -> None:
        self.start_count = 0
        self.stop_count = 0

    def start(self) -> None:
        self.start_count += 1

    def stop(self) -> None:
        self.stop_count += 1


class _StubResolver:
    """Resolver that records calls and optionally raises."""

    def __init__(self, side_effect: Exception | None = None) -> None:
        self.calls: list[Any] = []
        self._side_effect = side_effect

    def resolve_covers(self, item: Any) -> None:
        self.calls.append(item)
        if self._side_effect is not None:
            raise self._side_effect
        item._covers_lines = frozenset()


class _StubReporter:
    """Reporter that records write calls."""

    def __init__(self) -> None:
        self.write_calls: list[Any] = []

    def write(self, report: Any, output_dir: Any) -> None:
        self.write_calls.append((report, output_dir))


def _stub_getoption(name: str, default: Any = None) -> Any:
    return default


def _stub_getini(name: str) -> str:
    return {"coverage_stats_precision": "1"}.get(name, "")


def _make_stub_config() -> SimpleNamespace:
    return SimpleNamespace(
        pluginmanager=SimpleNamespace(hasplugin=lambda name: False),
        getoption=_stub_getoption,
        getini=_stub_getini,
    )


def _make_stub_customization() -> CoverageStatsCustomization:
    return CoverageStatsCustomization(_make_stub_config())


def _make_tracing_coord(
    *,
    tracer: _StubTracer | None = None,
    resolver: _StubResolver | None = None,
) -> tuple[TracingCoordinator, SessionStore, ProfilerContext, _StubTracer, _StubResolver]:
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=[])
    if tracer is None:
        tracer = _StubTracer()
    if resolver is None:
        resolver = _StubResolver()
    coord = TracingCoordinator(
        store, tracer, ctx, resolver, _make_stub_customization()  # type: ignore[arg-type]
    )
    return coord, store, ctx, tracer, resolver


def _make_reporting_coord(
    store: SessionStore | None = None,
    customization: CoverageStatsCustomization | None = None,
) -> ReportingCoordinator:
    if store is None:
        store = SessionStore()
    if customization is None:
        customization = _make_stub_customization()
    return ReportingCoordinator(store, customization)


# ---------------------------------------------------------------------------
# TracingCoordinator — pytest_runtest_setup
# ---------------------------------------------------------------------------


@covers(TracingCoordinator.pytest_runtest_setup)
def test_runtest_setup_sets_phase_item_and_clears_state():
    coord, _store, ctx, _tracer, _resolver = _make_tracing_coord()
    ctx.current_phase = "call"
    ctx.current_assert_count = 7
    ctx.current_test_lines.add(("/a.py", 1))

    item = SimpleNamespace(_covers_lines=frozenset({("/a.py", 5)}))
    coord.pytest_runtest_setup(item)  # type: ignore[arg-type]

    assert ctx.current_phase == "setup"
    assert ctx.current_test_item is item
    assert ctx.current_covers_lines == frozenset({("/a.py", 5)})
    assert ctx.current_assert_count == 0
    assert len(ctx.current_test_lines) == 0


@covers(TracingCoordinator.pytest_runtest_setup)
def test_runtest_setup_covers_defaults_to_empty_frozenset_when_absent():
    coord, _store, ctx, _tracer, _resolver = _make_tracing_coord()
    item = SimpleNamespace()  # no _covers_lines attribute
    coord.pytest_runtest_setup(item)  # type: ignore[arg-type]
    assert ctx.current_covers_lines == frozenset()


@covers(TracingCoordinator.pytest_runtest_setup)
def test_runtest_setup_calls_resolver_for_function_items(pytester):
    """resolve_covers is called for pytest.Function items (requires a real item).

    Uses pytester.getitems to collect a real pytest.Function in-process,
    avoiding the pytest Node construction deprecation.
    """
    items = pytester.getitems("def test_x(): pass")
    item = items[0]
    assert isinstance(item, pytest.Function)

    resolver = _StubResolver()
    coord, _store, _ctx, _tracer, _ = _make_tracing_coord(resolver=resolver)
    coord.pytest_runtest_setup(item)

    assert len(resolver.calls) == 1
    assert resolver.calls[0] is item


@covers(TracingCoordinator.pytest_runtest_setup)
def test_runtest_setup_skips_resolver_for_non_function_items():
    resolver = _StubResolver()
    coord, _store, _ctx, _tracer, _ = _make_tracing_coord(resolver=resolver)

    coord.pytest_runtest_setup(SimpleNamespace())  # type: ignore[arg-type]

    assert resolver.calls == []


@covers(TracingCoordinator.pytest_runtest_setup)
def test_runtest_setup_resolver_exception_propagates(pytester):
    """An exception from resolve_covers is not swallowed — it aborts the test setup."""
    items = pytester.getitems("def test_x(): pass")
    resolver = _StubResolver(side_effect=RuntimeError("boom"))
    coord, _store, _ctx, _tracer, _ = _make_tracing_coord(resolver=resolver)

    with pytest.raises(RuntimeError, match="boom"):
        coord.pytest_runtest_setup(items[0])


@covers(TracingCoordinator.pytest_runtest_setup)
def test_runtest_setup_noop_when_disabled():
    coord, _store, ctx, _tracer, resolver = _make_tracing_coord()
    coord._enabled = False
    ctx.current_phase = "call"

    coord.pytest_runtest_setup(SimpleNamespace())  # type: ignore[arg-type]

    assert ctx.current_phase == "call"   # unchanged
    assert resolver.calls == []


# ---------------------------------------------------------------------------
# TracingCoordinator — pytest_runtest_call
# ---------------------------------------------------------------------------


@covers(TracingCoordinator.pytest_runtest_call)
def test_runtest_call_sets_phase_to_call():
    coord, _store, ctx, _tracer, _resolver = _make_tracing_coord()
    ctx.current_phase = "setup"

    coord.pytest_runtest_call(SimpleNamespace())  # type: ignore[arg-type]

    assert ctx.current_phase == "call"


@covers(TracingCoordinator.pytest_runtest_call)
def test_runtest_call_noop_when_disabled():
    coord, _store, ctx, _tracer, _resolver = _make_tracing_coord()
    coord._enabled = False
    ctx.current_phase = "setup"

    coord.pytest_runtest_call(SimpleNamespace())  # type: ignore[arg-type]

    assert ctx.current_phase == "setup"  # unchanged


# ---------------------------------------------------------------------------
# TracingCoordinator — pytest_runtest_teardown
# ---------------------------------------------------------------------------


@covers(TracingCoordinator.pytest_runtest_teardown)
def test_runtest_teardown_resets_context_and_distributes_asserts():
    coord, store, ctx, _tracer, _resolver = _make_tracing_coord()
    fake_item = SimpleNamespace(nodeid="tests/test_mod.py::test_example")
    ctx.current_test_item = fake_item
    ctx.current_phase = "call"
    ctx.current_covers_lines = frozenset({("/a.py", 1)})
    ctx.current_assert_count = 3
    ctx.current_test_lines.add(("/a.py", 1))

    coord.pytest_runtest_teardown(fake_item, nextitem=None)  # type: ignore[arg-type]

    assert ctx.current_phase is None
    assert ctx.current_test_item is None
    assert ctx.current_covers_lines == frozenset()
    # distribute_asserts drains current_test_lines and resets assert_count
    assert ctx.current_assert_count == 0
    assert len(ctx.current_test_lines) == 0


@covers(TracingCoordinator.pytest_runtest_teardown)
def test_runtest_teardown_noop_when_disabled():
    coord, _store, ctx, _tracer, _resolver = _make_tracing_coord()
    coord._enabled = False
    ctx.current_phase = "call"
    fake_item = SimpleNamespace()
    ctx.current_test_item = fake_item

    coord.pytest_runtest_teardown(fake_item, nextitem=None)  # type: ignore[arg-type]

    assert ctx.current_phase == "call"     # unchanged
    assert ctx.current_test_item is fake_item  # unchanged


# ---------------------------------------------------------------------------
# TracingCoordinator — pytest_assertion_pass
# ---------------------------------------------------------------------------


@covers(TracingCoordinator.pytest_assertion_pass)
def test_assertion_pass_increments_assert_count_during_call_phase():
    coord, _store, ctx, _tracer, _resolver = _make_tracing_coord()
    ctx.current_phase = "call"
    ctx.current_test_item = SimpleNamespace()

    coord.pytest_assertion_pass(SimpleNamespace(), lineno=1, orig="x", expl="x")  # type: ignore[arg-type]

    assert ctx.current_assert_count == 1


@covers(TracingCoordinator.pytest_assertion_pass)
def test_assertion_pass_noop_when_disabled():
    coord, _store, ctx, _tracer, _resolver = _make_tracing_coord()
    coord._enabled = False
    ctx.current_phase = "call"
    ctx.current_test_item = SimpleNamespace()

    coord.pytest_assertion_pass(SimpleNamespace(), lineno=1, orig="x", expl="x")  # type: ignore[arg-type]

    assert ctx.current_assert_count == 0


# ---------------------------------------------------------------------------
# TracingCoordinator — pytest_sessionstart / pytest_collectstart
# ---------------------------------------------------------------------------


@covers(TracingCoordinator.pytest_sessionstart)
def test_sessionstart_starts_tracer():
    tracer = _StubTracer()
    coord, _store, _ctx, _, _resolver = _make_tracing_coord(tracer=tracer)

    coord.pytest_sessionstart(SimpleNamespace())  # type: ignore[arg-type]

    assert tracer.start_count == 1


@covers(TracingCoordinator.pytest_sessionstart)
def test_sessionstart_noop_when_disabled():
    tracer = _StubTracer()
    coord, _store, _ctx, _, _resolver = _make_tracing_coord(tracer=tracer)
    coord._enabled = False

    coord.pytest_sessionstart(SimpleNamespace())  # type: ignore[arg-type]

    assert tracer.start_count == 0


@covers(TracingCoordinator.pytest_collectstart)
def test_collectstart_starts_tracer():
    tracer = _StubTracer()
    coord, _store, _ctx, _, _resolver = _make_tracing_coord(tracer=tracer)

    coord.pytest_collectstart(SimpleNamespace())  # type: ignore[arg-type]

    assert tracer.start_count == 1


@covers(TracingCoordinator.pytest_collectstart)
def test_collectstart_noop_when_disabled():
    tracer = _StubTracer()
    coord, _store, _ctx, _, _resolver = _make_tracing_coord(tracer=tracer)
    coord._enabled = False

    coord.pytest_collectstart(SimpleNamespace())  # type: ignore[arg-type]

    assert tracer.start_count == 0


# ---------------------------------------------------------------------------
# TracingCoordinator — flush_pre_test_lines (static method)
# ---------------------------------------------------------------------------


@covers(TracingCoordinator.flush_pre_test_lines)
def test_flush_pre_test_lines_copies_lines_to_store():
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=[])
    ctx.pre_test_lines.add(("/a.py", 1))
    ctx.pre_test_lines.add(("/a.py", 2))

    TracingCoordinator.flush_pre_test_lines(ctx, store)

    ld1 = store.get_or_create(("/a.py", 1))
    ld2 = store.get_or_create(("/a.py", 2))
    assert ld1.incidental_executions == 1
    assert ld1.deliberate_executions == 1
    assert ld2.incidental_executions == 1
    assert ld2.deliberate_executions == 1


@covers(TracingCoordinator.flush_pre_test_lines)
def test_flush_pre_test_lines_does_not_overwrite_existing_entry():
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=[])
    # Pre-populate with call-phase data
    ld = store.get_or_create(("/a.py", 1))
    ld.deliberate_executions = 5
    ctx.pre_test_lines.add(("/a.py", 1))

    TracingCoordinator.flush_pre_test_lines(ctx, store)

    # Existing entry must be untouched
    assert ld.deliberate_executions == 5
    assert ld.incidental_executions == 0   # flush must not have overwritten it


@covers(TracingCoordinator.flush_pre_test_lines)
def test_flush_pre_test_lines_clears_the_pre_test_set():
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=[])
    ctx.pre_test_lines.add(("/a.py", 1))

    TracingCoordinator.flush_pre_test_lines(ctx, store)

    assert len(ctx.pre_test_lines) == 0


@covers(TracingCoordinator.flush_pre_test_lines)
def test_flush_pre_test_lines_empty_set_is_noop():
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=[])

    TracingCoordinator.flush_pre_test_lines(ctx, store)  # must not raise

    assert list(store.items()) == []


# ---------------------------------------------------------------------------
# ReportingCoordinator — pytest_testnodedown
# ---------------------------------------------------------------------------


def _make_node(raw: str | None) -> SimpleNamespace:
    wo: dict[str, str] = {}
    if raw is not None:
        wo["coverage_stats_data"] = raw
    return SimpleNamespace(workeroutput=wo)


def _serialise(path: str, lineno: int, ie: int = 0, de: int = 0) -> str:
    store = SessionStore()
    ld = store.get_or_create((path, lineno))
    ld.incidental_executions = ie
    ld.deliberate_executions = de
    return json.dumps(store.to_dict())


@covers(ReportingCoordinator.pytest_testnodedown)
def test_testnodedown_merges_worker_data():
    coord = _make_reporting_coord()
    raw = _serialise("/a.py", 10, ie=3, de=1)

    coord.pytest_testnodedown(_make_node(raw), error=None)  # type: ignore[arg-type]

    ld = coord._store.get_or_create(("/a.py", 10))
    assert ld.incidental_executions == 3
    assert ld.deliberate_executions == 1


@covers(ReportingCoordinator.pytest_testnodedown)
def test_testnodedown_merges_multiple_workers():
    coord = _make_reporting_coord()
    coord.pytest_testnodedown(_make_node(_serialise("/a.py", 1, ie=2)), error=None)  # type: ignore[arg-type]
    coord.pytest_testnodedown(_make_node(_serialise("/a.py", 1, ie=3)), error=None)  # type: ignore[arg-type]

    assert coord._store.get_or_create(("/a.py", 1)).incidental_executions == 5


@covers(ReportingCoordinator.pytest_testnodedown)
def test_testnodedown_missing_key_is_noop():
    coord = _make_reporting_coord()
    coord.pytest_testnodedown(_make_node(None), error=None)  # type: ignore[arg-type]
    assert list(coord._store.items()) == []


@covers(ReportingCoordinator.pytest_testnodedown)
def test_testnodedown_malformed_json_warns_not_raises():
    coord = _make_reporting_coord()

    with pytest.warns(UserWarning, match="coverage-stats"):
        coord.pytest_testnodedown(_make_node("not-json{{{"), error=None)  # type: ignore[arg-type]

    # Store must remain empty — bad data is discarded
    assert list(coord._store.items()) == []


@covers(ReportingCoordinator.pytest_testnodedown)
def test_testnodedown_noop_when_disabled():
    coord = _make_reporting_coord()
    coord._enabled = False

    coord.pytest_testnodedown(_make_node(_serialise("/a.py", 1, ie=1)), error=None)  # type: ignore[arg-type]

    assert list(coord._store.items()) == []


# ---------------------------------------------------------------------------
# ReportingCoordinator — pytest_sessionfinish
# ---------------------------------------------------------------------------


def _make_session_config(
    fmt: str = "",
    output: str = "coverage-stats-report",
    reporter_paths: str = "",
) -> SimpleNamespace:
    def _getoption(name: str, default: Any = None) -> Any:
        if name == "--coverage-stats-format":
            return fmt or default
        if name == "--coverage-stats-output":
            return output or default
        if name == "--coverage-stats-reporter":
            return reporter_paths or default
        return default

    def _getini(name: str) -> str:
        if name == "coverage_stats_format":
            return fmt
        if name == "coverage_stats_output_dir":
            return output
        if name == "coverage_stats_reporters":
            return reporter_paths
        return {"coverage_stats_precision": "1"}.get(name, "")

    return SimpleNamespace(
        pluginmanager=SimpleNamespace(hasplugin=lambda n: False),
        getoption=_getoption,
        getini=_getini,
    )


@covers(ReportingCoordinator.pytest_sessionfinish)
def test_sessionfinish_noop_when_disabled(tmp_path):
    coord = _make_reporting_coord()
    coord._enabled = False
    config = _make_session_config(output=str(tmp_path / "out"))
    session = SimpleNamespace(config=config)

    coord.pytest_sessionfinish(session, exitstatus=0)  # type: ignore[arg-type]

    assert not (tmp_path / "out").exists()


@covers(ReportingCoordinator.pytest_sessionfinish)
def test_sessionfinish_calls_reporter_write(tmp_path):
    """When a reporter is configured, its write() is called with the built report."""
    stub_reporter = _StubReporter()

    class _StubCustomization(CoverageStatsCustomization):
        """Customization that injects the stub reporter."""
        def get_reporters(self, formats, reporter_paths):
            return [("stub", stub_reporter)]
        def get_report_builder(self):
            from coverage_stats.reporters.report_data import DefaultReportBuilder
            return DefaultReportBuilder()
        def get_coverage_py_interop(self):
            return SimpleNamespace(inject_into_coverage_py=lambda store: None)

    store = SessionStore()
    customization = _StubCustomization(_make_stub_config())
    coord = ReportingCoordinator(store, customization)  # type: ignore[arg-type]

    config = _make_session_config(output=str(tmp_path / "out"))
    config.rootpath = tmp_path
    session = SimpleNamespace(config=config)

    coord.pytest_sessionfinish(session, exitstatus=0)  # type: ignore[arg-type]

    assert len(stub_reporter.write_calls) == 1


@covers(ReportingCoordinator.pytest_sessionfinish)
def test_sessionfinish_reporter_exception_warns_not_raises(tmp_path):
    """A reporter that raises must emit a warning, not abort the session."""

    class _BrokenReporter:
        def write(self, report: Any, output_dir: Any) -> None:
            raise RuntimeError("disk full")

    class _StubCustomization2:
        def get_reporters(self, formats, reporter_paths):
            return [("broken", _BrokenReporter())]
        def get_report_builder(self):
            from coverage_stats.reporters.report_data import DefaultReportBuilder
            return DefaultReportBuilder()
        def get_coverage_py_interop(self):
            return SimpleNamespace(inject_into_coverage_py=lambda store: None)

    store = SessionStore()
    customization = _StubCustomization2()
    coord = ReportingCoordinator(store, customization)  # type: ignore[arg-type]

    config = _make_session_config(output=str(tmp_path / "out"))
    config.rootpath = tmp_path
    session = SimpleNamespace(config=config)

    with pytest.warns(UserWarning, match="coverage-stats"):
        coord.pytest_sessionfinish(session, exitstatus=0)  # type: ignore[arg-type]
