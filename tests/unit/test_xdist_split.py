from __future__ import annotations

import json
from types import SimpleNamespace

from coverage_stats.plugin import (
    CoverageStatsPlugin,
    _is_xdist_controller,
    _is_xdist_worker,
)
from coverage_stats.store import SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plugin_manager(has_xdist: bool = False):
    """Return a minimal pluginmanager stub."""
    return SimpleNamespace(hasplugin=lambda name: name == "xdist" and has_xdist)


def _config_worker():
    """Config that looks like an xdist worker (has workerinput)."""
    return SimpleNamespace(
        workerinput={},
        workeroutput={},
        pluginmanager=_make_plugin_manager(has_xdist=True),
    )


def _config_controller():
    """Config that looks like an xdist controller (no workerinput, xdist registered)."""
    return SimpleNamespace(
        pluginmanager=_make_plugin_manager(has_xdist=True),
        option=SimpleNamespace(dist="load"),
        # Note: real controller configs do NOT have workeroutput — only workers do
    )


def _config_no_xdist():
    """Config for single-process run (no workerinput, xdist not registered)."""
    return SimpleNamespace(
        pluginmanager=_make_plugin_manager(has_xdist=False),
    )


# ---------------------------------------------------------------------------
# _is_xdist_worker
# ---------------------------------------------------------------------------


def test_is_xdist_worker_true_when_workerinput_present():
    config = _config_worker()
    assert _is_xdist_worker(config) is True


def test_is_xdist_worker_false_when_no_workerinput():
    config = _config_controller()
    assert _is_xdist_worker(config) is False


# ---------------------------------------------------------------------------
# _is_xdist_controller
# ---------------------------------------------------------------------------


def test_is_xdist_controller_true_when_xdist_registered_no_workerinput():
    config = _config_controller()
    assert _is_xdist_controller(config) is True


def test_is_xdist_controller_false_when_xdist_not_registered():
    config = _config_no_xdist()
    assert _is_xdist_controller(config) is False


def test_is_xdist_controller_false_when_is_worker():
    config = _config_worker()
    assert _is_xdist_controller(config) is False


# ---------------------------------------------------------------------------
# pytest_testnodedown
# ---------------------------------------------------------------------------


def _make_enabled_plugin_with_store() -> CoverageStatsPlugin:
    plugin = CoverageStatsPlugin()
    plugin._enabled = True
    plugin._store = SessionStore()
    return plugin


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
    plugin = _make_enabled_plugin_with_store()

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

    plugin.pytest_testnodedown(node=node1, error=None)
    plugin.pytest_testnodedown(node=node2, error=None)

    ld = plugin._store._data[("foo.py", 10)]
    assert ld.incidental_executions == 5   # 2 + 3
    assert ld.deliberate_executions == 1   # 1 + 0
    assert ld.incidental_asserts == 1      # 0 + 1
    assert ld.deliberate_asserts == 0


def test_pytest_testnodedown_skips_gracefully_when_key_missing():
    plugin = _make_enabled_plugin_with_store()
    node = SimpleNamespace(workeroutput={})  # no coverage_stats_data key
    # Must not raise
    plugin.pytest_testnodedown(node=node, error=None)
    assert plugin._store._data == {}


def test_pytest_testnodedown_noop_when_disabled():
    plugin = CoverageStatsPlugin()
    plugin._enabled = False
    plugin._store = SessionStore()

    node = SimpleNamespace(
        workeroutput={
            "coverage_stats_data": _serialise_store({("bar.py", 5): [1, 0, 0, 0]})
        }
    )
    plugin.pytest_testnodedown(node=node, error=None)
    # Store must remain untouched because plugin is disabled
    assert plugin._store._data == {}


# ---------------------------------------------------------------------------
# Worker pytest_sessionfinish
# ---------------------------------------------------------------------------


def test_worker_sessionfinish_populates_workeroutput():
    plugin = _make_enabled_plugin_with_store()
    # Seed the store with one line
    ld = plugin._store.get_or_create(("src/app.py", 20))
    ld.incidental_executions = 4

    config = _config_worker()
    session = SimpleNamespace(config=config)

    plugin.pytest_sessionfinish(session=session, exitstatus=0)

    raw = config.workeroutput.get("coverage_stats_data")
    assert raw is not None
    parsed = json.loads(raw)
    # Just verify at least one entry present and value is correct
    assert len(parsed) == 1
    values = list(parsed.values())[0]
    assert values[0] == 4  # incidental_executions


def test_worker_sessionfinish_does_not_create_output_dir(tmp_path):
    plugin = _make_enabled_plugin_with_store()

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
    plugin.pytest_sessionfinish(session=session, exitstatus=0)

    # Reporters must NOT have been called — directory should not exist
    assert not output_subdir.exists()


# ---------------------------------------------------------------------------
# Controller pytest_configure creates store but no tracer
# ---------------------------------------------------------------------------


def test_controller_configure_creates_store_but_no_tracer():
    """Simulate what pytest_configure does for the controller path."""
    # We call it manually via the logic in plugin.py rather than monkey-patching pytest
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
        # No workeroutput — real controller configs don't have this attribute
        _coverage_stats_ctx=None,
    )
    # Simulate getoption returning True for --coverage-stats
    config.getoption = lambda name, default=None: True if name == "--coverage-stats" else default
    config.getini = lambda name: ""

    pytest_configure(config)

    plugin = registered.get("coverage-stats-plugin")
    assert plugin is not None
    assert plugin._enabled is True
    assert plugin._tracer is None
    assert isinstance(plugin._store, SessionStore)
    assert config._coverage_stats_ctx is None
