from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from coverage_stats.covers import CoverageStatsResolver
    from coverage_stats.plugin import CoverageStatsCustomization
    from coverage_stats.profiler import LineTracer, ProfilerContext
    from coverage_stats.store import SessionStore


class TracingCoordinator:
    """Manages line tracing, assert counting, and per-test context.

    Registered on xdist workers and single-process runs; NOT registered on
    xdist controllers (which have no tracer).  Owns the tracer lifecycle,
    per-test phase transitions, and assert distribution.  On xdist workers,
    also serializes the store to workeroutput in pytest_sessionfinish.
    """

    def __init__(
        self,
        store: SessionStore,
        tracer: LineTracer,
        ctx: ProfilerContext,
        resolver: CoverageStatsResolver,
        customization: CoverageStatsCustomization,
        *,
        coverage_py_active: bool = False,
        orig_read_pyc: object = None,
    ) -> None:
        self._enabled: bool = True
        self._coverage_py_active = coverage_py_active
        self._store = store
        self._tracer = tracer
        self._ctx = ctx
        self._resolver = resolver
        self._customization = customization
        self._orig_read_pyc: object = orig_read_pyc

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
        if self._orig_read_pyc is not None:
            import _pytest.assertion.rewrite as _rewrite
            _rewrite._read_pyc = self._orig_read_pyc  # type: ignore[assignment]
            self._orig_read_pyc = None
        if self._tracer is not None:
            self._tracer.start()
        # On Python < 3.12 our tracer displaces coverage.py's C tracer, so
        # coverage.py records nothing.  Patch cov.save() here — after the tracer
        # is installed but before any tests run — so our data is injected the
        # moment coverage.py writes to disk.
        if self._coverage_py_active and sys.version_info < (3, 12):
            store = self._store
            ctx = self._ctx

            def _flush() -> None:
                self.flush_pre_test_lines(ctx, store)

            self._customization.get_coverage_py_interop().patch_coverage_save(store, _flush)

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        """Resolve @covers metadata and reset per-test tracking state."""
        if not self._enabled:
            return
        if isinstance(item, pytest.Function):
            self._resolver.resolve_covers(item)
        self._ctx.current_test_item = item
        self._ctx.current_covers_lines = getattr(item, "_covers_lines", frozenset())
        self._ctx.current_phase = "setup"
        self._ctx.current_test_lines.clear()
        self._ctx.current_assert_count = 0

    def pytest_runtest_call(self, item: pytest.Item) -> None:
        """Advance the phase to 'call' so the tracer records lines during test execution."""
        if not self._enabled:
            return
        self._ctx.current_phase = "call"

    def pytest_runtest_teardown(self, item: pytest.Item, nextitem: pytest.Item | None) -> None:
        """Distribute accumulated assert counts to covered lines, then reset context."""
        if not self._enabled:
            return
        self._ctx.current_phase = "teardown"
        self._ctx.distribute_asserts(self._store)
        self._ctx.current_phase = None
        self._ctx.current_test_item = None
        self._ctx.current_covers_lines = frozenset()

    def pytest_assertion_pass(self, item: pytest.Item, lineno: int, orig: str, expl: str) -> None:
        """Increment the assert counter each time an assertion passes during 'call'."""
        if not self._enabled:
            return
        self._ctx.record_assertion()

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
        """Stop tracing and flush pre-test lines; serialize store if running as an xdist worker."""
        if not self._enabled:
            return
        import json
        config = session.config
        if self._tracer is not None:
            self._tracer.stop()
        self.flush_pre_test_lines(self._ctx, self._store)
        if self._customization.is_xdist_worker():
            # On Python < 3.12 each xdist worker displaces coverage.py's C tracer
            # so the worker's own .coverage.<pid> file would be empty.  Inject our
            # data here, before pytest-cov's pytest_sessionfinish saves the file.
            if self._coverage_py_active and sys.version_info < (3, 12):
                self._customization.get_coverage_py_interop().inject_into_coverage_py(self._store)
            config.workeroutput["coverage_stats_data"] = json.dumps(self._store.to_dict())  # type: ignore[attr-defined]

    @staticmethod
    def flush_pre_test_lines(ctx: ProfilerContext, store: SessionStore) -> None:
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
            if key not in store:
                ld = store.get_or_create(key)
                ld.incidental_executions = 1
                ld.deliberate_executions = 1
        ctx.pre_test_lines.clear()
