from __future__ import annotations


class CoverageStatsPlugin:
    def __init__(self) -> None:
        self._enabled: bool = False

    def pytest_collection_finish(self, session) -> None:
        if not self._enabled:
            return
        raise NotImplementedError

    def pytest_runtest_setup(self, item) -> None:
        if not self._enabled:
            return
        from coverage_stats.covers import resolve_covers
        resolve_covers(item)

    def pytest_runtest_call(self, item) -> None:
        if not self._enabled:
            return
        raise NotImplementedError

    def pytest_runtest_teardown(self, item, nextitem) -> None:
        if not self._enabled:
            return
        raise NotImplementedError

    def pytest_assertion_pass(self, item, lineno, orig, expl) -> None:
        if not self._enabled:
            return
        raise NotImplementedError

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if not self._enabled:
            return
        raise NotImplementedError


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--coverage-stats",
        action="store_true",
        default=False,
        help="Enable coverage-stats plugin",
    )


def pytest_configure(config) -> None:
    plugin = CoverageStatsPlugin()
    plugin._enabled = bool(config.getoption("--coverage-stats", default=False))
    config._coverage_stats_ctx = None
    config.pluginmanager.register(plugin, "coverage-stats-plugin")
