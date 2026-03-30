from __future__ import annotations

import importlib
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import pytest

if TYPE_CHECKING:
    from coverage_stats.profiler import LineTracer, ProfilerContext
    from coverage_stats.store import SessionStore

_DEFAULT_STORE = "coverage_stats.store.SessionStore"
_DEFAULT_PROFILER_CONTEXT = "coverage_stats.profiler.ProfilerContext"
_DEFAULT_LINE_TRACER = "coverage_stats.profiler.LineTracer"
_DEFAULT_REPORT_BUILDER = "coverage_stats.reporters.report_data.DefaultReportBuilder"


def _load_store_class(dotted_path: str) -> type[SessionStore]:
    module_path, sep, class_name = dotted_path.rpartition(".")
    if not sep:
        raise ValueError(
            f"Invalid store class path {dotted_path!r}: expected 'module.path.ClassName'"
        )
    module = importlib.import_module(module_path)
    return getattr(module, class_name)  # type: ignore[no-any-return]


def _load_profiler_context_class(dotted_path: str) -> type[ProfilerContext]:
    module_path, sep, class_name = dotted_path.rpartition(".")
    if not sep:
        raise ValueError(
            f"Invalid profiler context class path {dotted_path!r}: expected 'module.path.ClassName'"
        )
    module = importlib.import_module(module_path)
    return getattr(module, class_name)  # type: ignore[no-any-return]


def _load_line_tracer_class(dotted_path: str) -> type[LineTracer]:
    module_path, sep, class_name = dotted_path.rpartition(".")
    if not sep:
        raise ValueError(
            f"Invalid line tracer class path {dotted_path!r}: expected 'module.path.ClassName'"
        )
    module = importlib.import_module(module_path)
    return getattr(module, class_name)  # type: ignore[no-any-return]


def _load_report_builder_class(dotted_path: str) -> type:
    module_path, sep, class_name = dotted_path.rpartition(".")
    if not sep:
        raise ValueError(
            f"Invalid report builder class path {dotted_path!r}: expected 'module.path.ClassName'"
        )
    module = importlib.import_module(module_path)
    return getattr(module, class_name)  # type: ignore[no-any-return]


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
        self._store: SessionStore | None = None
        self._tracer: LineTracer | None = None
        self._orig_read_pyc: object = None  # stored during collection to force rewrite
        self._report_builder_cls: type = object  # replaced in pytest_configure

    @pytest.hookimpl(trylast=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        """Start the line tracer now that all plugins have finished configuring.

        Deferring tracer.start() from pytest_configure to here avoids tracing
        the heavyweight module imports that other plugins trigger during their
        own pytest_configure hooks (e.g. _pytest.debugging loading pdb + asyncio),
        which otherwise accounts for several seconds of pure tracing overhead.

        trylast=True ensures we install our sys.settrace callback after every
        other plugin (notably coverage.py / pytest-cov) has installed its own
        tracer.  That puts us on top of the chain: we receive all frame events
        first and forward them to whatever was installed before us.  Without
        this, coverage.py's C-extension tracer can end up on top and may not
        call our Python-level tracer back, leaving the store permanently empty.
        """
        if not self._enabled:
            return
        if _is_xdist_controller(session.config):
            return
        if self._tracer is not None:
            self._tracer.start()

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """Called after collection is finished; restore _read_pyc so the cache works normally."""
        if not self._enabled:
            return
        if self._orig_read_pyc is not None:
            import _pytest.assertion.rewrite as _rewrite
            _rewrite._read_pyc = self._orig_read_pyc  # type: ignore[assignment]
            self._orig_read_pyc = None

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
        assert self._store is not None
        ctx.distribute_asserts(self._store)
        # Reset after teardown completes
        ctx.current_phase = None
        ctx.current_test_item = None

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
        import json
        raw = getattr(node, "workeroutput", {}).get("coverage_stats_data")
        if raw:
            assert self._store is not None
            worker_store = type(self._store).from_dict(json.loads(raw))
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
            ctx = getattr(config, "_coverage_stats_ctx", None)
            if ctx is not None:
                _flush_pre_test_lines(ctx, self._store)
            config.workeroutput["coverage_stats_data"] = json.dumps(self._store.to_dict())  # type: ignore[attr-defined]
            return
        # controller or single-process: call reporters
        if self._tracer is not None:
            self._tracer.stop()
        assert self._store is not None
        ctx = getattr(config, "_coverage_stats_ctx", None)
        if ctx is not None:
            _flush_pre_test_lines(ctx, self._store)
        fmt_str = config.getoption("--coverage-stats-format") or config.getini("coverage_stats_format")
        formats = [f.strip() for f in (fmt_str or "").split(",") if f.strip()]
        out_str = config.getoption("--coverage-stats-output") or config.getini("coverage_stats_output_dir")
        output_dir = Path(out_str).resolve()
        precision_opt = config.getoption("--coverage-stats-precision")
        precision: int = int(precision_opt) if precision_opt is not None else int(config.getini("coverage_stats_precision") or 1)
        reporter_str = config.getoption("--coverage-stats-reporter") or config.getini("coverage_stats_reporters")
        reporter_paths = [r.strip() for r in (reporter_str or "").split(",") if r.strip()]

        from coverage_stats.reporters import get_reporter, load_reporter_class, _instantiate_reporter
        known_kwargs: dict[str, object] = {"precision": precision}

        reporters = []
        for fmt in formats:
            reporter = get_reporter(fmt, known_kwargs)
            if reporter is not None:
                reporters.append((fmt, reporter))
            else:
                warnings.warn(f"coverage-stats: unknown format {fmt!r}, skipping")
        for path in reporter_paths:
            try:
                cls = load_reporter_class(path)
                reporters.append((path, _instantiate_reporter(cls, known_kwargs)))
            except Exception as exc:
                warnings.warn(f"coverage-stats: failed to load reporter {path!r}: {exc}")

        report = self._report_builder_cls().build(self._store, config)
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
        "--coverage-stats-store",
        type=str,
        default=None,
        help=f"SessionStore class to use (module.path.ClassName, default: {_DEFAULT_STORE})",
    )
    parser.addini(
        "coverage_stats_store",
        help=f"SessionStore class to use (module.path.ClassName, default: {_DEFAULT_STORE})",
        default=_DEFAULT_STORE,
    )
    parser.addoption(
        "--coverage-stats-profiler-context",
        type=str,
        default=None,
        help=f"ProfilerContext class to use (module.path.ClassName, default: {_DEFAULT_PROFILER_CONTEXT})",
    )
    parser.addini(
        "coverage_stats_profiler_context",
        help=f"ProfilerContext class to use (module.path.ClassName, default: {_DEFAULT_PROFILER_CONTEXT})",
        default=_DEFAULT_PROFILER_CONTEXT,
    )
    parser.addoption(
        "--coverage-stats-line-tracer",
        type=str,
        default=None,
        help=f"LineTracer class to use (module.path.ClassName, default: {_DEFAULT_LINE_TRACER})",
    )
    parser.addini(
        "coverage_stats_line_tracer",
        help=f"LineTracer class to use (module.path.ClassName, default: {_DEFAULT_LINE_TRACER})",
        default=_DEFAULT_LINE_TRACER,
    )
    parser.addoption(
        "--coverage-stats-report-builder",
        type=str,
        default=None,
        help=f"ReportBuilder class to use (module.path.ClassName, default: {_DEFAULT_REPORT_BUILDER})",
    )
    parser.addini(
        "coverage_stats_report_builder",
        help=f"ReportBuilder class to use (module.path.ClassName, default: {_DEFAULT_REPORT_BUILDER})",
        default=_DEFAULT_REPORT_BUILDER,
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

    store_path = config.getoption("--coverage-stats-store") or config.getini("coverage_stats_store") or _DEFAULT_STORE
    store_cls = _load_store_class(store_path)
    ctx_path = config.getoption("--coverage-stats-profiler-context") or config.getini("coverage_stats_profiler_context") or _DEFAULT_PROFILER_CONTEXT
    ctx_cls = _load_profiler_context_class(ctx_path)
    tracer_path = config.getoption("--coverage-stats-line-tracer") or config.getini("coverage_stats_line_tracer") or _DEFAULT_LINE_TRACER
    tracer_cls = _load_line_tracer_class(tracer_path)
    builder_path = config.getoption("--coverage-stats-report-builder") or config.getini("coverage_stats_report_builder") or _DEFAULT_REPORT_BUILDER
    report_builder_cls = _load_report_builder_class(builder_path)

    if _is_xdist_controller(config):
        store = store_cls()
        config._coverage_stats_ctx = None  # type: ignore[attr-defined]
        plugin._store = store
        plugin._tracer = None
        plugin._report_builder_cls = report_builder_cls
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

    ctx = ctx_cls(source_dirs=source_dirs)
    store = store_cls()
    tracer = tracer_cls(ctx, store)

    config._coverage_stats_ctx = ctx  # type: ignore[attr-defined]
    plugin._store = store
    plugin._tracer = tracer
    plugin._report_builder_cls = report_builder_cls

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
