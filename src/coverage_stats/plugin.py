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
    """Central pytest plugin that wires together line tracing, assert counting, and reporting.

    ## 1. How it plugs into pytest

    The plugin is registered as a pytest entry point (``pytest11``) in ``pyproject.toml``,
    so pytest loads it automatically whenever the package is installed.  It only activates
    when the ``--coverage-stats`` flag is passed; otherwise all hooks return immediately.

    ``pytest_configure`` (a module-level hook below the class) instantiates the plugin,
    performs role-specific setup (single-process, xdist worker, or xdist controller), and
    registers the instance with pytest's plugin manager so its hooks are called.

    ## 2. How it collects stats

    Line-level execution is recorded by ``LineTracer`` (``profiler.py``), a ``sys.settrace``
    callback that fires on every ``line`` event while a test's ``call`` phase is active.
    The tracer runs only on files under the configured source directories.

    Assertion counts are collected via ``pytest_assertion_pass``, which pytest calls for
    every passing assertion when ``enable_assertion_pass_hook`` is ``True``.  The plugin
    forces this ini flag on in ``pytest_configure`` so it does not need to be set manually.
    Each call increments ``ProfilerContext.current_assert_count`` for the active test.

    The two-category distinction (deliberate vs. incidental) comes from ``@covers``:
    if a test is decorated with ``@covers(some_function)``, lines inside ``some_function``
    are marked deliberate; all other traced lines are incidental.  This metadata is resolved
    by ``covers.resolve_covers`` during ``pytest_runtest_setup`` and stored on the item as
    ``item._covers_lines`` (a ``frozenset`` of ``(abs_path, lineno)`` pairs).

    ## 3. How it stores stats

    Each traced ``(abs_path, lineno)`` pair maps to a ``LineData`` record in a
    ``SessionStore`` (``store.py``).  ``LineData`` holds four integers:
    ``incidental_executions``, ``deliberate_executions``, ``incidental_asserts``,
    and ``deliberate_asserts``.

    Assert counts are not recorded per-line as assertions fire; instead they are
    distributed at teardown by ``assert_counter.distribute_asserts``, which spreads
    ``current_assert_count`` across every line that was executed during that test's
    ``call`` phase (stored in ``ProfilerContext.current_test_lines``).

    ## 4. How it is used by its clients

    Test authors interact with the plugin through two surfaces:

    - ``@covers(*refs)`` decorator (``covers.py``) — marks which functions or classes a
      test deliberately targets.  Refs can be live objects or dotted strings resolved
      lazily at setup time.
    - CLI / ini options — ``--coverage-stats`` to enable, ``--coverage-stats-format``
      (``html``, ``json``, ``csv``, comma-separated) and ``--coverage-stats-output`` for
      the output directory.  All options have ``coverage_stats_*`` ini equivalents.

    ## 5. How it interacts with the rest of the project

    - ``profiler.LineTracer`` / ``ProfilerContext`` — the tracer is started in
      ``pytest_configure`` and stopped in ``pytest_sessionfinish``.  ``ProfilerContext``
      is attached to ``config._coverage_stats_ctx`` so every hook can reach it via the
      item's config without needing a direct reference to the plugin instance.
    - ``store.SessionStore`` — owned by the plugin instance.  On xdist workers it is
      populated locally; ``pytest_sessionfinish`` serialises it to JSON in
      ``config.workeroutput``.  The controller receives each worker's payload in
      ``pytest_testnodedown`` and merges it into its own store via ``SessionStore.merge``.
    - ``reporters`` (``html``, ``json_reporter``, ``csv_reporter``) — called from
      ``pytest_sessionfinish`` on the controller / single-process node after the tracer
      has stopped, passing the fully-merged store and the pytest config.
    """

    def __init__(self) -> None:
        self._enabled: bool = False
        self._store: SessionStore | None = None
        self._tracer: LineTracer | None = None

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """Called after collection is finished."""
        if not self._enabled:
            return

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        """Resolve @covers metadata and reset per-test tracking state."""
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
        """Advance the phase to 'call' so the tracer records lines during test execution."""
        if not self._enabled:
            return
        ctx = item.config._coverage_stats_ctx  # type: ignore[attr-defined]
        ctx.current_phase = "call"

    def pytest_runtest_teardown(self, item: pytest.Item, nextitem: pytest.Item | None) -> None:
        """Distribute accumulated assert counts to covered lines, then reset context."""
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
        """Increment the assert counter each time an assertion passes during 'call'."""
        if not self._enabled:
            return
        from coverage_stats.assert_counter import record_assertion
        ctx = item.config._coverage_stats_ctx  # type: ignore[attr-defined]
        record_assertion(ctx)

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node: _XdistWorkerNode, error: BaseException | None) -> None:
        """Merge coverage data from an xdist worker into the controller's store."""
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
        """Stop tracing and write reports; on xdist workers, serialize data for the controller."""
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

    # pytest_assertion_pass is only called when this ini flag is True.
    # Force it on so assert counts are recorded correctly.
    inicache = getattr(config, "_inicache", None)
    if isinstance(inicache, dict):
        inicache["enable_assertion_pass_hook"] = True

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
