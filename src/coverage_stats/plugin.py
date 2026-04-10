from __future__ import annotations

import importlib
import inspect
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from coverage_stats.covers import CoverageStatsResolver
    from coverage_stats.executable_lines import ExecutableLinesAnalyzer
    from coverage_stats.profiler import LineTracer, ProfilerContext
    from coverage_stats.reporters.base import Reporter
    from coverage_stats.reporters.coverage_py_interop import CoveragePyInteropProto
    from coverage_stats.reporters.report_data import ReportBuilder
    from coverage_stats.store import SessionStore
    from coverage_stats.tracing_coordinator import TracingCoordinator
    from coverage_stats.reporting_coordinator import ReportingCoordinator

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
    coverage_py_interop = "coverage_stats.reporters.coverage_py_interop.CoveragePyInterop"
    tracing_coordinator = "coverage_stats.tracing_coordinator.TracingCoordinator"
    reporting_coordinator = "coverage_stats.reporting_coordinator.ReportingCoordinator"
    resolver = "coverage_stats.covers.CoverageStatsResolver"
    executable_lines_analyzer = "coverage_stats.executable_lines.ExecutableLinesAnalyzer"

    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        precision_opt = config.getoption("--coverage-stats-precision")
        self.precision: int = (
            int(precision_opt) if precision_opt is not None
            else int(config.getini("coverage_stats_precision") or 1)
        )
        self.coverage_py_active: bool = config.pluginmanager.hasplugin("pytest_cov")

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
        return self._load_class(self.report_builder)(self.get_executable_lines_analyzer())  # type: ignore[no-any-return]

    def get_coverage_py_interop(self) -> CoveragePyInteropProto:
        return self._load_class(self.coverage_py_interop)()  # type: ignore[no-any-return]

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

    def get_resolver(self) -> CoverageStatsResolver:
        return self._load_class(self.resolver)(self.get_executable_lines_analyzer())  # type: ignore[no-any-return]

    def get_reporting_coordinator(self, store: SessionStore) -> ReportingCoordinator:
        cls: type[ReportingCoordinator] = self._load_class(self.reporting_coordinator)
        return cls(store, self, coverage_py_active=self.coverage_py_active)

    def get_source_dirs(self) -> list[str]:
        """Resolve the source directories to trace, relative to the rootdir."""
        raw_source = self.config.getini("coverage_stats_source")
        rootdir = Path(str(self.config.rootpath))
        candidate_dirs = [
            (rootdir / d).resolve() if not Path(d).is_absolute() else Path(d).resolve()
            for d in (raw_source.split() if isinstance(raw_source, str) else raw_source)
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
        source_dirs = self.get_source_dirs()
        ctx = self.get_profiler_context(source_dirs)
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
