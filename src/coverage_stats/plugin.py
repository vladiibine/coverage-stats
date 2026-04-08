from __future__ import annotations

import importlib
import json
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pytest
from coverage_stats.reporters.base import get_reporter
from coverage_stats.covers import resolve_covers

if TYPE_CHECKING:
    from coverage_stats.profiler import LineTracer, ProfilerContext
    from coverage_stats.reporters.base import Reporter, _instantiate_reporter
    from coverage_stats.reporters.report_data import (
        CoveragePyInteropProto,
        ReportBuilder,
    )
    from coverage_stats.store import SessionStore

_DEFAULT_CUSTOMIZATION = "coverage_stats.plugin.CoverageStatsCustomization"


class CoverageStatsCustomization:
    """Single entry point for all class-level customizations.

    Each ``get_*`` method loads its class from the corresponding dotted-path
    constant and returns a fresh instance.  Subclass and override the
    constants or the getter methods to swap in custom implementations.

    The ``precision`` parameter (passed at construction) is forwarded to
    reporters that accept it.
    """

    store = "coverage_stats.store.SessionStore"
    profiler_context = "coverage_stats.profiler.ProfilerContext"
    line_tracer = (
        "coverage_stats.profiler.MonitoringLineTracer"
        if sys.version_info >= (3, 12)
        else "coverage_stats.profiler.LineTracer"
    )
    report_builder = "coverage_stats.reporters.report_data.DefaultReportBuilder"
    coverage_py_interop = "coverage_stats.reporters.report_data.CoveragePyInterop"

    def __init__(self, precision: int = 1) -> None:
        self.precision = precision

    def _load_class(self, dotted_path: str) -> type:
        module_path, sep, class_name = dotted_path.rpartition(".")
        if not sep:
            raise ValueError(
                f"Invalid class path {dotted_path!r}: expected 'module.path.ClassName'"
            )
        module = importlib.import_module(module_path)
        return getattr(module, class_name)  # type: ignore[no-any-return]

    def get_store(self) -> SessionStore:
        cls: type[SessionStore] = self._load_class(self.store)
        return cls()

    def get_profiler_context(self, source_dirs: list[str]) -> ProfilerContext:
        cls: type[ProfilerContext] = self._load_class(self.profiler_context)
        return cls(source_dirs=source_dirs)

    def get_line_tracer(self, context: ProfilerContext, store: SessionStore) -> LineTracer:
        cls: type[LineTracer] = self._load_class(self.line_tracer)
        return cls(context, store)

    def get_report_builder(self) -> ReportBuilder:
        return self._load_class(self.report_builder)()  # type: ignore[no-any-return]

    def get_coverage_py_interop(self) -> CoveragePyInteropProto:
        return self._load_class(self.coverage_py_interop)()  # type: ignore[no-any-return]

    def get_reporters(self, formats: list[str], reporter_paths: list[str]) -> list[tuple[str, Reporter]]:
        """Load built-in and custom reporters, passing precision where accepted."""
        known_kwargs: dict[str, object] = {"precision": self.precision}

        reporters: list[tuple[str, Reporter]] = []
        for fmt in formats:
            reporter = get_reporter(fmt, known_kwargs)
            if reporter is not None:
                reporters.append((fmt, reporter))
            else:
                warnings.warn(f"coverage-stats: unknown format {fmt!r}, skipping")
        for path in reporter_paths:
            try:
                cls = self._load_class(path)
                reporters.append((path, _instantiate_reporter(cls, known_kwargs)))
            except Exception as exc:
                warnings.warn(f"coverage-stats: failed to load reporter {path!r}: {exc}")
        return reporters


class _XdistWorkerNode(Protocol):
    workeroutput: dict[str, str]


def _flush_pre_test_lines(ctx: ProfilerContext, store: SessionStore) -> None:
    """Copy pre-test lines into the store as incidental + deliberate (if not already present).

    Lines executed before any test phase (module imports, module-level code,
    bodies of functions called at module level) are recorded in
    ``ctx.pre_test_lines`` by the tracer.  This drains that set into the store
    so reporters see them as covered.  Existing store entries (from call-phase
    tracing) are not overwritten.

    Pre-test lines count as both incidental and deliberate: importing a module
    to run tests is itself a deliberate act, so ``def`` statements and other
    module-level code should not penalise deliberate coverage.
    """
    for key in ctx.pre_test_lines:
        if key not in store._data:
            ld = store.get_or_create(key)
            ld.incidental_executions = 1
            ld.deliberate_executions = 1
    ctx.pre_test_lines.clear()


def _is_xdist_worker(config: pytest.Config) -> bool:
    return hasattr(config, "workerinput")


def _is_xdist_controller(config: pytest.Config) -> bool:
    if _is_xdist_worker(config):
        return False
    if not config.pluginmanager.hasplugin("xdist"):
        return False
    # xdist installed but not active (no -n flag) → treat as single-process
    return getattr(config.option, "dist", "no") != "no"


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
    distributed at teardown by ``ProfilerContext.distribute_asserts``, which spreads
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
        self._coverage_py_active: bool = False
        self._store: SessionStore | None = None
        self._tracer: LineTracer | None = None
        self._orig_read_pyc: object = None  # stored during collection to force rewrite
        self._customization: CoverageStatsCustomization | None = None  # set in pytest_configure

    @pytest.hookimpl(trylast=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        """First tracer install — captures lines executed during collection.

        trylast=True ensures coverage.py has already installed its own tracer
        before we install on top of it.  Lines executed during collection
        (def/class statements, module-level code) fire line events here and
        are recorded into ProfilerContext.pre_test_lines.
        """
        if not self._enabled:
            return
        if _is_xdist_controller(session.config):
            return
        if self._tracer is not None:
            self._tracer.start()

    @pytest.hookimpl(trylast=True)
    def pytest_collectstart(self, collector: pytest.Collector) -> None:
        """Reinstall the tracer at the start of each file collection.

        Coverage.py reinstalls its C tracer before each collected module,
        displacing ours.  Hooking here with trylast=True puts us back on top
        *after* coverage.py so we receive line events when the module is
        imported (capturing pre-test lines like ``def``/``class`` statements).
        """
        if not self._enabled:
            return
        if _is_xdist_controller(collector.config):
            return
        if self._tracer is not None:
            self._tracer.start()

    @pytest.hookimpl(trylast=True)
    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """Reinstall the tracer after coverage.py's collection stop/restart cycle.

        Coverage.py performs a stop()/start() cycle around collection which
        displaces our tracer.  Calling start() again here puts us back on top
        after that cycle has completed, so we receive all line events during
        test execution.  start() is safe to call twice — it snapshots
        sys.gettrace() and reinstalls cleanly each time.

        We also restore the _read_pyc hook here so the pyc cache works normally
        for subsequent test collection runs.
        """
        if not self._enabled:
            return
        if _is_xdist_controller(session.config):
            return
        if self._orig_read_pyc is not None:
            import _pytest.assertion.rewrite as _rewrite
            _rewrite._read_pyc = self._orig_read_pyc  # type: ignore[assignment]
            self._orig_read_pyc = None
        if self._tracer is not None:
            self._tracer.start()
        # On Python < 3.12 our LineTracer displaces coverage.py's C tracer, so
        # coverage.py records nothing.  Patch cov.save() here — after the tracer
        # is installed but before any tests run — so our data is injected the
        # moment coverage.py writes to disk.  This is ordering-independent: it
        # works regardless of which hook (pytest_runtestloop or
        # pytest_sessionfinish) triggers the actual save.
        if self._coverage_py_active and sys.version_info < (3, 12):
            assert self._store is not None
            config = session.config
            store = self._store

            def _flush() -> None:
                ctx = getattr(config, "_coverage_stats_ctx", None)
                if ctx is not None:
                    _flush_pre_test_lines(ctx, store)

            assert self._customization is not None
            self._customization.get_coverage_py_interop().patch_coverage_save(store, _flush)

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        """Resolve @covers metadata and reset per-test tracking state."""
        if not self._enabled:
            return
        if isinstance(item, pytest.Function):
            resolve_covers(item)
        ctx = item.config._coverage_stats_ctx  # type: ignore[attr-defined]
        ctx.current_test_item = item
        # Cache covers_lines on ctx so the tracer hot path reads a direct field
        # instead of calling getattr(item, "_covers_lines", frozenset()) per line.
        ctx.current_covers_lines = getattr(item, "_covers_lines", frozenset())
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
        assert self._store is not None
        ctx.distribute_asserts(self._store)
        # Reset after teardown completes
        ctx.current_phase = None
        ctx.current_test_item = None
        ctx.current_covers_lines = frozenset()

    def pytest_assertion_pass(self, item: pytest.Item, lineno: int, orig: str, expl: str) -> None:
        """Increment the assert counter each time an assertion passes during 'call'."""
        if not self._enabled:
            return
        ctx = item.config._coverage_stats_ctx  # type: ignore[attr-defined]
        ctx.record_assertion()

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node: _XdistWorkerNode, error: BaseException | None) -> None:
        """Merge coverage data from an xdist worker into the controller's store."""
        if not self._enabled:
            return
        raw = getattr(node, "workeroutput", {}).get("coverage_stats_data")
        if raw:
            assert self._store is not None
            worker_store = type(self._store).from_dict(json.loads(raw))
            self._store.merge(worker_store)

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
        """Stop tracing and write reports; on xdist workers, serialize data for the controller.

        tryfirst=True ensures we run before pytest-cov's pytest_sessionfinish so
        that any data we inject into coverage.py's CoverageData object is present
        before coverage.py calls cov.save() and generates its report.  This
        covers both the live-report scenario (coverage.py reports immediately)
        and the deferred scenario (coverage.py saves .coverage for a later
        `coverage report` command).
        """
        if not self._enabled:
            return
        config = session.config
        if _is_xdist_worker(config):
            if self._tracer is not None:
                self._tracer.stop()
            assert self._store is not None
            ctx = getattr(config, "_coverage_stats_ctx", None)
            if ctx is not None:
                _flush_pre_test_lines(ctx, self._store)
            # On Python < 3.12 each xdist worker displaces coverage.py's C tracer
            # so the worker's own .coverage.<pid> file would be empty.  Inject our
            # data here, before pytest-cov's pytest_sessionfinish saves the file.
            if self._coverage_py_active and sys.version_info < (3, 12):
                assert self._customization is not None
                self._customization.get_coverage_py_interop().inject_into_coverage_py(self._store)
            config.workeroutput["coverage_stats_data"] = json.dumps(self._store.to_dict())  # type: ignore[attr-defined]
            return
        # controller or single-process: stop tracer and flush pre-test lines
        if self._tracer is not None:
            self._tracer.stop()
        assert self._store is not None
        ctx = getattr(config, "_coverage_stats_ctx", None)
        if ctx is not None:
            _flush_pre_test_lines(ctx, self._store)
        # On Python < 3.12 coverage.py's C tracer was displaced by ours, so its
        # data object is empty for the test-execution phase; inject our data so
        # its reports are accurate.  On 3.12+ both tools use sys.monitoring
        # independently and each has its own complete data — no injection needed.
        if self._coverage_py_active and sys.version_info < (3, 12):
            assert self._customization is not None
            self._customization.get_coverage_py_interop().inject_into_coverage_py(self._store)
        fmt_str = config.getoption("--coverage-stats-format") or config.getini("coverage_stats_format")
        formats = [f.strip() for f in (fmt_str or "").split(",") if f.strip()]
        out_str = config.getoption("--coverage-stats-output") or config.getini("coverage_stats_output_dir")
        output_dir = Path(out_str).resolve()
        reporter_str = config.getoption("--coverage-stats-reporter") or config.getini("coverage_stats_reporters")
        reporter_paths = [r.strip() for r in (reporter_str or "").split(",") if r.strip()]

        assert self._customization is not None
        reporters = self._customization.get_reporters(formats, reporter_paths)

        report = self._customization.get_report_builder().build(self._store, config)
        for name, reporter in reporters:
            try:
                reporter.write(report, output_dir)
            except Exception as exc:
                warnings.warn(f"coverage-stats: reporter {name!r} failed: {exc}")


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
    parser.addoption(
        "--coverage-stats-precision",
        type=int,
        default=None,
        help="Decimal places for percentages in HTML reports (default: 1)",
    )
    parser.addoption(
        "--coverage-stats-reporter",
        type=str,
        default=None,
        help="Comma-separated list of reporter classes (module.path.ClassName)",
    )
    parser.addini(
        "coverage_stats_source",
        help="Source directories to profile (space-separated). Defaults to 'src'.",
        default="src",
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
    parser.addini(
        "coverage_stats_precision",
        help="Decimal places for percentages in HTML reports (default: 1)",
        default="1",
    )
    parser.addini(
        "coverage_stats_reporters",
        help="Comma-separated list of reporter classes (module.path.ClassName)",
        default="",
    )
    parser.addoption(
        "--coverage-stats-customization",
        type=str,
        default=None,
        help=f"CoverageStatsCustomization class to use (module.path.ClassName, default: {_DEFAULT_CUSTOMIZATION})",
    )
    parser.addini(
        "coverage_stats_customization",
        help=f"CoverageStatsCustomization class to use (module.path.ClassName, default: {_DEFAULT_CUSTOMIZATION})",
        default=_DEFAULT_CUSTOMIZATION,
    )


def pytest_configure(config: pytest.Config) -> None:
    plugin = CoverageStatsPlugin()
    plugin._enabled = bool(config.getoption("--coverage-stats", default=False))
    plugin._coverage_py_active = config.pluginmanager.hasplugin("pytest_cov")

    if not plugin._enabled:
        config._coverage_stats_ctx = None  # type: ignore[attr-defined]
        config.pluginmanager.register(plugin, "coverage-stats-plugin")
        return

    # pytest_assertion_pass is only called when this ini flag is True.
    # Force it on so assert counts are recorded correctly.
    inicache = getattr(config, "_inicache", None)
    if isinstance(inicache, dict):
        inicache["enable_assertion_pass_hook"] = True

    # Load the customization class (single entry point for all class overrides).
    customization_path = config.getoption("--coverage-stats-customization") or config.getini("coverage_stats_customization") or _DEFAULT_CUSTOMIZATION
    customization_module, _, customization_cls_name = customization_path.rpartition(".")
    if not customization_module:
        raise ValueError(
            f"Invalid customization class path {customization_path!r}: expected 'module.path.ClassName'"
        )
    customization_cls = getattr(importlib.import_module(customization_module), customization_cls_name)
    precision_opt = config.getoption("--coverage-stats-precision")
    precision: int = int(precision_opt) if precision_opt is not None else int(config.getini("coverage_stats_precision") or 1)
    customization: CoverageStatsCustomization = customization_cls(precision=precision)
    plugin._customization = customization

    if _is_xdist_controller(config):
        store = customization.get_store()
        config._coverage_stats_ctx = None  # type: ignore[attr-defined]
        plugin._store = store
        plugin._tracer = None
        config.pluginmanager.register(plugin, "coverage-stats-plugin")
        return

    # worker or single-process: full setup
    raw_source = config.getini("coverage_stats_source")
    rootdir = Path(str(config.rootpath))
    candidate_dirs = [
        (rootdir / d).resolve() if not Path(d).is_absolute() else Path(d).resolve()
        for d in (raw_source.split() if isinstance(raw_source, str) else raw_source)
        if d
    ]
    # Only include directories that actually exist; if none exist fall back to
    # the default "profile everything non-stdlib" behaviour (empty list).
    source_dirs = [str(p) for p in candidate_dirs if p.is_dir()]

    ctx = customization.get_profiler_context(source_dirs)
    store = customization.get_store()
    tracer = customization.get_line_tracer(ctx, store)

    config._coverage_stats_ctx = ctx  # type: ignore[attr-defined]
    plugin._store = store
    plugin._tracer = tracer

    # Bypass pytest's assertion-rewrite .pyc cache during test collection.
    # pytest caches rewritten bytecode without including `enable_assertion_pass_hook`
    # in the cache key, so if tests ran previously without this flag the cached .pyc
    # files won't contain hook call sites and pytest_assertion_pass never fires.
    # Returning None from _read_pyc forces a fresh rewrite for every test module
    # collected this session.  The hook is restored in pytest_collection_finish.
    import _pytest.assertion.rewrite as _rewrite
    plugin._orig_read_pyc = _rewrite._read_pyc
    _rewrite._read_pyc = lambda *args, **kwargs: None

    # tracer.start() is deferred to pytest_sessionstart to avoid tracing
    # heavyweight imports by other plugins during their pytest_configure hooks.
    config.pluginmanager.register(plugin, "coverage-stats-plugin")
