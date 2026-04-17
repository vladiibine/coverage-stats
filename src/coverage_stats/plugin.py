from __future__ import annotations

import importlib
import inspect
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import pytest

if TYPE_CHECKING:
    from coverage_stats.covers import CoverageStatsResolver
    from coverage_stats.executable_lines import ExecutableLinesAnalyzer
    from coverage_stats.reporters.branch_analysis import BranchWalker
    from coverage_stats.profiler import LineTracer, ProfilerContext
    from coverage_stats.reporters.base import Reporter
    from coverage_stats.reporters.coverage_py_interop import CoveragePyInteropProto
    from coverage_stats.reporters.report_data import ReportBuilder
    from coverage_stats.store import SessionStore
    from coverage_stats.tracing_coordinator import TracingCoordinator
    from coverage_stats.reporting_coordinator import ReportingCoordinator

_DEFAULT_CUSTOMIZATION = "coverage_stats.plugin.CoverageStatsCustomization"

# State created in pytest_load_initial_conftests and consumed in configure().
# Using a list as a mutable container so inner functions can mutate it.
_early_state: Optional[dict[str, Any]] = None


class _MetaPathTracerEnsurer:
    """sys.meta_path finder that reinstalls the line tracer before each module import.

    On Python < 3.12, coverage.py's C tracer (installed via sys.settrace) displaces
    our tracer whenever it reinstalls itself.  This finder is registered at
    ``sys.meta_path[0]`` during ``pytest_load_initial_conftests`` so that, for
    every subsequent module import (including conftest-time ``import httpx``),
    we put our tracer back on top before the module code executes.

    ``start()`` has an O(1) fast path when the tracer is already on top, so the
    overhead per import is a single ``sys.gettrace()`` comparison in the common case.

    Removed in ``TracingCoordinator.pytest_sessionstart`` once conftest loading is
    complete and the ``pytest_collectstart`` reinstall mechanism takes over.
    """

    def __init__(self, tracer: Any) -> None:
        self._tracer = tracer

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> None:
        self._tracer.start()
        return None

    # Python 3.3 legacy hook — must be present to satisfy the MetaPathFinder ABC.
    def find_module(self, fullname: str, path: Any = None) -> None:
        return None


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
    coverage_py_interop = "coverage_stats.reporters.coverage_py_interop.CoveragePyInterop"
    tracing_coordinator = "coverage_stats.tracing_coordinator.TracingCoordinator"
    reporting_coordinator = "coverage_stats.reporting_coordinator.ReportingCoordinator"
    resolver = "coverage_stats.covers.CoverageStatsResolver"
    executable_lines_analyzer = "coverage_stats.executable_lines.ExecutableLinesAnalyzer"
    branch_walker = "coverage_stats.reporters.branch_analysis.BranchWalker"

    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        precision_opt = config.getoption("--coverage-stats-precision")
        self.precision: int = (
            int(precision_opt) if precision_opt is not None
            else int(config.getini("coverage_stats_precision") or 1)
        )
        self.coverage_py_active: bool = config.pluginmanager.hasplugin("pytest_cov")
        no_track_ids_opt = config.getoption("--coverage-stats-no-track-test-ids", default=False)
        no_track_ids_ini = config.getini("coverage_stats_no_track_test_ids")
        disabled = bool(no_track_ids_opt) or str(no_track_ids_ini).lower() in ("true", "1", "yes")
        self.track_test_ids: bool = not disabled
        self.track_test_folders: bool = bool(config.getoption("--coverage-stats-track-test-folders", default=False))

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

    def get_profiler_context(self, source_dirs: list[str], exclude_dirs: list[str] | None = None) -> ProfilerContext:
        cls: type[ProfilerContext] = self._load_class(self.profiler_context)
        return cls(source_dirs=source_dirs, exclude_dirs=exclude_dirs or [], track_test_ids=self.track_test_ids)

    def get_line_tracer(self, context: ProfilerContext, store: SessionStore) -> LineTracer:
        cls: type[LineTracer] = self._load_class(self.line_tracer)
        return cls(context, store)

    def get_report_builder(self) -> ReportBuilder:
        return self._load_class(self.report_builder)(self.get_executable_lines_analyzer(), self.get_branch_walker())  # type: ignore[no-any-return]

    def get_coverage_py_interop(self) -> CoveragePyInteropProto:
        return self._load_class(self.coverage_py_interop)(self.get_branch_walker())  # type: ignore[no-any-return]

    def get_tracing_coordinator(
        self,
        store: SessionStore,
        tracer: LineTracer,
        ctx: ProfilerContext,
        orig_read_pyc: object = None,
    ) -> TracingCoordinator:
        cls: type[TracingCoordinator] = self._load_class(self.tracing_coordinator)
        return cls(store, tracer, ctx, self.get_resolver(), self, coverage_py_active=self.coverage_py_active, orig_read_pyc=orig_read_pyc)

    def get_executable_lines_analyzer(self) -> ExecutableLinesAnalyzer:
        return self._load_class(self.executable_lines_analyzer)()  # type: ignore[no-any-return]

    def get_branch_walker(self) -> BranchWalker:
        return self._load_class(self.branch_walker)()  # type: ignore[no-any-return]

    def get_resolver(self) -> CoverageStatsResolver:
        return self._load_class(self.resolver)(self.get_executable_lines_analyzer())  # type: ignore[no-any-return]

    def get_reporting_coordinator(self, store: SessionStore) -> ReportingCoordinator:
        cls: type[ReportingCoordinator] = self._load_class(self.reporting_coordinator)
        return cls(store, self, coverage_py_active=self.coverage_py_active)

    def get_source_dirs(self, cli_source: str | None = None) -> list[str]:
        """Resolve the source directories to trace, relative to the rootdir.

        Resolution order:
        1. *cli_source* — value parsed from ``--coverage-stats-source`` in the
           raw args list by ``pytest_load_initial_conftests`` (most reliable at
           early-config time).
        2. ``coverage_stats_source`` ini value.
        3. Project rootdir (broadest fallback).
        """
        raw_source = cli_source if cli_source is not None else self.config.getini("coverage_stats_source")
        rootdir = Path(str(self.config.rootpath))
        candidate_dirs = [
            (rootdir / d).resolve() if not Path(d).is_absolute() else Path(d).resolve()
            for d in (raw_source.split() if isinstance(raw_source, str) else raw_source)
            if d
        ]
        resolved = [str(p) for p in candidate_dirs if p.is_dir()]
        if not resolved:
            resolved = [str(rootdir.resolve())]
        return resolved

    def get_exclude_dirs(self) -> list[str]:
        """Resolve the directories to exclude from tracing.

        When ``--coverage-stats-track-test-folders`` is set, no directories are
        excluded.  Otherwise the ``coverage_stats_exclude`` ini value (default
        ``"tests"``) is resolved relative to the rootdir and any existing
        directories are excluded.
        """
        if self.track_test_folders:
            return []
        raw_exclude = self.config.getini("coverage_stats_exclude")
        rootdir = Path(str(self.config.rootpath))
        candidate_dirs = [
            (rootdir / d).resolve() if not Path(d).is_absolute() else Path(d).resolve()
            for d in (raw_exclude.split() if isinstance(raw_exclude, str) else raw_exclude)
            if d
        ]
        return [str(p) for p in candidate_dirs if p.is_dir()]

    def is_xdist_worker(self) -> bool:
        return hasattr(self.config, "workerinput")

    def is_xdist_controller(self) -> bool:
        if self.is_xdist_worker():
            return False
        if not self.config.pluginmanager.hasplugin("xdist"):
            return False
        # xdist installed but not active (no -n flag) → treat as single-process
        return getattr(self.config.option, "dist", "no") != "no"

    def configure(self) -> None:
        """Set up and register all plugin components with pytest.

        Called from ``pytest_configure`` immediately after the customization is
        instantiated.  Override to take full control of the setup process;
        override individual ``get_*`` methods for finer-grained customization.
        """
        # pytest_assertion_pass is only called when this ini flag is True.
        # Force it on so assert counts are recorded correctly.
        inicache = getattr(self.config, "_inicache", None)
        if isinstance(inicache, dict):
            inicache["enable_assertion_pass_hook"] = True

        if self.is_xdist_controller():
            # Controller: only merge worker data and write reports — no tracing.
            self.config.pluginmanager.register(
                self.get_reporting_coordinator(self.get_store()),
                "coverage-stats-reporting",
            )
            return

        # Worker or single-process: full tracing setup.
        # Reuse objects created in pytest_load_initial_conftests if available.
        # That early hook starts the tracer before conftest files are imported,
        # capturing module-level pre-test lines from conftest-time imports.
        global _early_state
        if _early_state is not None:
            store = _early_state["store"]
            ctx = _early_state["ctx"]
            tracer = _early_state["tracer"]
            _early_state = None
        else:
            source_dirs = self.get_source_dirs()
            exclude_dirs = self.get_exclude_dirs()
            ctx = self.get_profiler_context(source_dirs, exclude_dirs)
            store = self.get_store()
            tracer = self.get_line_tracer(ctx, store)

        # Bypass pytest's assertion-rewrite .pyc cache during test collection.
        # pytest caches rewritten bytecode without including `enable_assertion_pass_hook`
        # in the cache key, so if tests ran previously without this flag the cached .pyc
        # files won't contain hook call sites and pytest_assertion_pass never fires.
        # Returning None from _read_pyc forces a fresh rewrite for every test module
        # collected this session.  The hook is restored in TracingCoordinator.pytest_collection_finish.
        import _pytest.assertion.rewrite as _rewrite
        orig_read_pyc = _rewrite._read_pyc
        _rewrite._read_pyc = lambda *args, **kwargs: None

        tracing = self.get_tracing_coordinator(store, tracer, ctx, orig_read_pyc=orig_read_pyc)

        if not self.is_xdist_worker():
            # Single-process: register reporting BEFORE tracing so that pytest's LIFO
            # ordering for tryfirst hooks runs TracingCoordinator.pytest_sessionfinish
            # first (stops tracer, flushes pre-test lines) before ReportingCoordinator
            # builds the report.
            self.config.pluginmanager.register(
                self.get_reporting_coordinator(store),
                "coverage-stats-reporting",
            )

        # tracer.start() is deferred to pytest_sessionstart to avoid tracing
        # heavyweight imports by other plugins during their pytest_configure hooks.
        self.config.pluginmanager.register(tracing, "coverage-stats-tracing")

    def _instantiate_reporter(self, cls: type[Reporter]) -> Reporter:
        """Construct a reporter, injecting known kwargs the class accepts."""
        if cls.__init__ is object.__init__:
            return cls()
        known_kwargs: dict[str, Any] = {"precision": self.precision}
        sig = inspect.signature(cls.__init__)
        has_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        if has_var_keyword:
            return cls(**known_kwargs)
        filtered = {k: v for k, v in known_kwargs.items() if k in sig.parameters}
        return cls(**filtered)

    def get_reporter(self, fmt: str) -> Reporter | None:
        """Return a reporter instance for a built-in format name, or None if unknown."""
        if fmt == "html":
            from coverage_stats.reporters.html import HtmlReporter
            return self._instantiate_reporter(HtmlReporter)
        if fmt == "json":
            from coverage_stats.reporters.json_reporter import JsonReporter
            return self._instantiate_reporter(JsonReporter)
        if fmt == "csv":
            from coverage_stats.reporters.csv_reporter import CsvReporter
            return self._instantiate_reporter(CsvReporter)
        return None

    def get_reporters(self, formats: list[str], reporter_paths: list[str]) -> list[tuple[str, Reporter]]:
        """Load built-in and custom reporters."""
        reporters: list[tuple[str, Reporter]] = []
        for fmt in formats:
            reporter = self.get_reporter(fmt)
            if reporter is not None:
                reporters.append((fmt, reporter))
            else:
                warnings.warn(f"coverage-stats: unknown format {fmt!r}, skipping")
        for path in reporter_paths:
            try:
                reporters.append((path, self._instantiate_reporter(self._load_class(path))))
            except Exception as exc:
                warnings.warn(f"coverage-stats: failed to load reporter {path!r}: {exc}")
        return reporters


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
    parser.addoption(
        "--coverage-stats-source",
        type=str,
        default=None,
        help="Source directories to trace (space-separated). Overrides coverage_stats_source ini value.",
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
    parser.addoption(
        "--coverage-stats-no-track-test-ids",
        action="store_true",
        default=False,
        help="Disable tracking of test node IDs per executed line (reduces memory usage).",
    )
    parser.addini(
        "coverage_stats_no_track_test_ids",
        help="Disable tracking of test node IDs per executed line (true/false, default: false).",
        default="false",
    )
    parser.addoption(
        "--coverage-stats-track-test-folders",
        action="store_true",
        default=False,
        help="Include test folders in the coverage-stats report (excluded by default).",
    )
    parser.addini(
        "coverage_stats_exclude",
        help="Directories to exclude from tracing (space-separated, default: 'tests').",
        default="tests",
    )


def pytest_load_initial_conftests(early_config: pytest.Config, parser: pytest.Parser, args: list[str]) -> None:
    """Start the line tracer before conftest.py files are imported.

    pytest_load_initial_conftests fires after all normal-tier hooks have run
    (including coverage.py's tracer installation) but before pytest's own trylast
    implementation loads conftest files.  We install the tracer here AND register
    a sys.meta_path finder that reinstalls it before every subsequent module import
    — this ensures we are on top of any coverage.py C tracer displacement when
    conftest-time imports like ``import httpx`` execute.

    The objects created here (store, ctx, tracer) are stored in ``_early_state``
    and reused by ``CoverageStatsCustomization.configure()`` in ``pytest_configure``
    so they are not recreated.
    """
    global _early_state
    if "--coverage-stats" not in args:
        return

    # Parse --coverage-stats-source from the raw args list.  getoption() is
    # unreliable at early_config time for plugin-registered options; the raw
    # args list is always accurate.
    cli_source: str | None = None
    _prefix = "--coverage-stats-source="
    for _arg in args:
        if _arg.startswith(_prefix):
            cli_source = _arg[len(_prefix):]
            break

    try:
        customization_path = (
            early_config.getini("coverage_stats_customization")
            or _DEFAULT_CUSTOMIZATION
        )
        customization_module, _, customization_cls_name = customization_path.rpartition(".")
        if not customization_module:
            return
        customization_cls: type[CoverageStatsCustomization] = getattr(
            importlib.import_module(customization_module), customization_cls_name
        )
        customization = customization_cls(early_config)

        if customization.is_xdist_controller():
            return

        source_dirs = customization.get_source_dirs(cli_source=cli_source)
        exclude_dirs = customization.get_exclude_dirs()
        store = customization.get_store()
        ctx = customization.get_profiler_context(source_dirs, exclude_dirs)
        tracer = customization.get_line_tracer(ctx, store)
        tracer.start()

        # Register a meta_path finder so we reinstall our tracer before each
        # subsequent module import.  On Python < 3.12, coverage.py's C tracer
        # displaces us; the finder guarantees we are on top when any module
        # (including conftest imports) is executed.
        ensurer = _MetaPathTracerEnsurer(tracer)
        sys.meta_path.insert(0, ensurer)
        ctx.meta_path_ensurer = ensurer

        _early_state = {"store": store, "ctx": ctx, "tracer": tracer}
    except Exception:
        # If early setup fails for any reason, fall back to the normal path in
        # pytest_configure/configure() which starts the tracer in pytest_sessionstart.
        _early_state = None


def pytest_configure(config: pytest.Config) -> None:
    """Hook to plug into the pytest plugin system.

    By design, we just retrieve the customization class and call .configure() on it, to allow users to
    customize things to the maximum extent possible.
    """
    if not config.getoption("--coverage-stats", default=False):
        return
    customization_path = (
        config.getoption("--coverage-stats-customization")
        or config.getini("coverage_stats_customization")
        or _DEFAULT_CUSTOMIZATION
    )
    customization_module, _, customization_cls_name = customization_path.rpartition(".")
    if not customization_module:
        raise ValueError(
            f"Invalid customization class path {customization_path!r}: expected 'module.path.ClassName'"
        )
    customization_cls: type[CoverageStatsCustomization] = getattr(
        importlib.import_module(customization_module), customization_cls_name
    )
    customization_cls(config).configure()
