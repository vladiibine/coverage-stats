from __future__ import annotations

import json
from types import SimpleNamespace

from coverage_stats.covers import CoverageStatsResolver
from coverage_stats.plugin import CoverageStatsCustomization
from coverage_stats.profiler import LineTracer, ProfilerContext
from coverage_stats.tracing_coordinator import TracingCoordinator
from coverage_stats.reporting_coordinator import ReportingCoordinator
from coverage_stats.store import SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stub_config() -> SimpleNamespace:
    return SimpleNamespace(
        pluginmanager=SimpleNamespace(hasplugin=lambda name: False),
        getoption=lambda name, default=None: default,
        getini=lambda name: {"coverage_stats_precision": "1"}.get(name, ""),
    )


def _make_stub_customization() -> CoverageStatsCustomization:
    return CoverageStatsCustomization(_make_stub_config())


def _make_plugin_manager(has_xdist: bool = False):
    """Return a minimal pluginmanager stub."""
    return SimpleNamespace(hasplugin=lambda name: name == "xdist" and has_xdist)


def _stub_getoption(name, default=None):
    return default


def _stub_getini(name):
    return {"coverage_stats_precision": "1"}.get(name, "")


def _config_worker():
    """Config that looks like an xdist worker (has workerinput)."""
    return SimpleNamespace(
        workerinput={},
        workeroutput={},
        pluginmanager=_make_plugin_manager(has_xdist=True),
        getoption=_stub_getoption,
        getini=_stub_getini,
    )


def _config_controller():
    """Config that looks like an xdist controller (no workerinput, xdist registered)."""
    return SimpleNamespace(
        pluginmanager=_make_plugin_manager(has_xdist=True),
        option=SimpleNamespace(dist="load"),
        getoption=_stub_getoption,
        getini=_stub_getini,
    )


def _config_no_xdist():
    """Config for single-process run (no workerinput, xdist not registered)."""
    return SimpleNamespace(
        pluginmanager=_make_plugin_manager(has_xdist=False),
        getoption=_stub_getoption,
        getini=_stub_getini,
    )


# ---------------------------------------------------------------------------
# _is_xdist_worker
# ---------------------------------------------------------------------------


def test_is_xdist_worker_true_when_workerinput_present():
    assert CoverageStatsCustomization(_config_worker()).is_xdist_worker() is True


def test_is_xdist_worker_false_when_no_workerinput():
    assert CoverageStatsCustomization(_config_controller()).is_xdist_worker() is False


# ---------------------------------------------------------------------------
# is_xdist_controller
# ---------------------------------------------------------------------------


def test_is_xdist_controller_true_when_xdist_registered_no_workerinput():
    assert CoverageStatsCustomization(_config_controller()).is_xdist_controller() is True


def test_is_xdist_controller_false_when_xdist_not_registered():
    assert CoverageStatsCustomization(_config_no_xdist()).is_xdist_controller() is False


def test_is_xdist_controller_false_when_is_worker():
    assert CoverageStatsCustomization(_config_worker()).is_xdist_controller() is False


# ---------------------------------------------------------------------------
# pytest_testnodedown (ReportingCoordinator)
# ---------------------------------------------------------------------------


def _make_enabled_reporting_coordinator() -> ReportingCoordinator:
    return ReportingCoordinator(SessionStore(), _make_stub_customization())


def _serialise_store(data: dict) -> str:
    """Build a SessionStore from raw {key: counts} dict, return JSON string."""
    store = SessionStore()
    for (path, lineno), counts in data.items():
        ld = store.get_or_create((path, lineno))
        ld.incidental_executions = counts[0]
        ld.deliberate_executions = counts[1]
        ld.incidental_asserts = counts[2]
        ld.deliberate_asserts = counts[3]
    return json.dumps(store.to_dict())


def test_pytest_testnodedown_merges_worker_store():
    coord = _make_enabled_reporting_coordinator()

    # Worker 1 contributes (foo.py, 10): [2, 1, 0, 0]
    node1 = SimpleNamespace(
        workeroutput={
            "coverage_stats_data": _serialise_store({("foo.py", 10): [2, 1, 0, 0]})
        }
    )
    # Worker 2 contributes (foo.py, 10): [3, 0, 1, 0]
    node2 = SimpleNamespace(
        workeroutput={
            "coverage_stats_data": _serialise_store({("foo.py", 10): [3, 0, 1, 0]})
        }
    )

    coord.pytest_testnodedown(node=node1, error=None)
    coord.pytest_testnodedown(node=node2, error=None)

    ld = coord._store.get_or_create(("foo.py", 10))
    assert ld.incidental_executions == 5   # 2 + 3
    assert ld.deliberate_executions == 1   # 1 + 0
    assert ld.incidental_asserts == 1      # 0 + 1
    assert ld.deliberate_asserts == 0


def test_pytest_testnodedown_skips_gracefully_when_key_missing():
    coord = _make_enabled_reporting_coordinator()
    node = SimpleNamespace(workeroutput={})  # no coverage_stats_data key
    # Must not raise
    coord.pytest_testnodedown(node=node, error=None)
    assert list(coord._store.items()) == []


def test_pytest_testnodedown_noop_when_disabled():
    coord = ReportingCoordinator(SessionStore(), _make_stub_customization())
    coord._enabled = False

    node = SimpleNamespace(
        workeroutput={
            "coverage_stats_data": _serialise_store({("bar.py", 5): [1, 0, 0, 0]})
        }
    )
    coord.pytest_testnodedown(node=node, error=None)
    # Store must remain untouched because coordinator is disabled
    assert list(coord._store.items()) == []


# ---------------------------------------------------------------------------
# Worker pytest_sessionfinish (TracingCoordinator)
# ---------------------------------------------------------------------------


def _make_enabled_tracing_coordinator(config=None) -> TracingCoordinator:
    if config is None:
        config = _make_stub_config()
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=[])
    tracer = LineTracer(ctx, store)
    return TracingCoordinator(store, tracer, ctx, CoverageStatsResolver(), CoverageStatsCustomization(config))


def test_worker_sessionfinish_populates_workeroutput():
    config = _config_worker()
    coord = _make_enabled_tracing_coordinator(config)
    # Seed the store with one line
    ld = coord._store.get_or_create(("src/app.py", 20))
    ld.incidental_executions = 4

    session = SimpleNamespace(config=config)

    coord.pytest_sessionfinish(session=session, exitstatus=0)

    raw = config.workeroutput.get("coverage_stats_data")
    assert raw is not None
    parsed = json.loads(raw)
    # Just verify at least one entry present and value is correct
    assert len(parsed) == 1
    values = list(parsed.values())[0]
    assert values[0] == 4  # incidental_executions


def test_worker_sessionfinish_does_not_create_output_dir(tmp_path):
    coord = _make_enabled_tracing_coordinator()

    config = _config_worker()
    # Provide a getoption/getini that would be used by reporters
    output_subdir = tmp_path / "coverage-output"
    config.getoption = lambda name, default=None: (
        "json" if name == "--coverage-stats-format" else
        str(output_subdir) if name == "--coverage-stats-output" else
        default
    )
    config.getini = lambda name: ""

    session = SimpleNamespace(config=config)
    coord.pytest_sessionfinish(session=session, exitstatus=0)

    # Reporters must NOT have been called — directory should not exist
    assert not output_subdir.exists()


# ---------------------------------------------------------------------------
# Controller pytest_configure creates store but no tracer
# ---------------------------------------------------------------------------


def test_controller_configure_creates_reporting_coordinator_only():
    """Simulate what pytest_configure does for the controller path."""
    from coverage_stats.plugin import pytest_configure  # noqa: PLC0415

    registered = {}

    class FakePluginManager:
        def hasplugin(self, name):
            return name == "xdist"

        def register(self, plugin, name):
            registered[name] = plugin

    config = SimpleNamespace(
        pluginmanager=FakePluginManager(),
        option=SimpleNamespace(dist="load"),
    )
    config.getoption = lambda name, default=None: True if name == "--coverage-stats" else default
    config.getini = lambda name: ""

    pytest_configure(config)

    # Controller: only a ReportingCoordinator is registered, no TracingCoordinator
    reporting = registered.get("coverage-stats-reporting")
    assert reporting is not None
    assert isinstance(reporting, ReportingCoordinator)
    assert reporting._enabled is True
    assert isinstance(reporting._store, SessionStore)

    # No tracing coordinator should be registered for the controller
    assert registered.get("coverage-stats-tracing") is None
