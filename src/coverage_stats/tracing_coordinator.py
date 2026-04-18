from __future__ import annotations

import sys
from pathlib import Path
from types import FrameType
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
        """Remove the early meta_path ensurer and reinstall the tracer.

        By the time pytest_sessionstart fires, all conftest files have been loaded
        (that happens in pytest_load_initial_conftests).  We no longer need the
        sys.meta_path ensurer — the pytest_collectstart reinstall mechanism takes
        over for test-module imports.  We remove it here to avoid the per-import
        overhead for the rest of the session.

        trylast=True ensures coverage.py has already installed its own tracer
        before we install on top of it.
        """
        if not self._enabled:
            return
        # Conftest loading is done — remove the meta_path ensurer.
        ensurer = self._ctx.meta_path_ensurer
        if ensurer is not None:
            try:
                sys.meta_path.remove(ensurer)
            except ValueError:
                pass
            self._ctx.meta_path_ensurer = None
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

    def _assertion_frame_is_app_code(self) -> bool:
        """Walk the call stack to check whether the passing assertion is in app code.

        pytest_assertion_pass fires for every rewritten assertion — including those
        in app modules registered via pytest.register_assert_rewrite().  Walking the
        stack lets us identify the frame that contains the assert statement and check
        whether its file falls inside the configured source dirs.

        Returns True (skip this assertion) when:
        - the first non-internal user-code frame is inside source_dirs, AND
        - it is not excluded by exclude_dirs (test dirs), AND
        - its filename does not match a test-file pattern (test_*.py / *_test.py /
          conftest.py) — this guard keeps the filter correct when source_dirs is
          broad (e.g. ".") and test files live alongside source files.

        Returns False (count this assertion) in all other cases, including when
        source_dirs is empty (no filtering configured).
        """
        source_dirs = self._ctx.source_dirs
        if not source_dirs:
            return False

        exclude_dirs = self._ctx.exclude_dirs

        # Frame 0 = this method, frame 1 = pytest_assertion_pass, frame 2 = caller.
        frame: FrameType | None = sys._getframe(2)
        while frame is not None:
            co_filename = frame.f_code.co_filename
            if not co_filename.startswith("<"):
                # Skip pytest, pluggy, and coverage_stats internals.
                if (
                    "_pytest" not in co_filename
                    and "pluggy" not in co_filename
                    and "coverage_stats" not in co_filename
                ):
                    basename = Path(co_filename).name
                    # Test infrastructure files: always count their assertions.
                    if (
                        basename.startswith("test_")
                        or basename.endswith("_test.py")
                        or basename == "conftest.py"
                    ):
                        return False

                    if "site-packages" in co_filename:
                        return False

                    filename = str(Path(co_filename).resolve())

                    if exclude_dirs and any(
                        filename == d or filename.startswith(d + "/")
                        for d in exclude_dirs
                    ):
                        return False

                    return any(
                        filename == d or filename.startswith(d + "/")
                        for d in source_dirs
                    )
            frame = frame.f_back
        return False

    def pytest_assertion_pass(self, item: pytest.Item, lineno: int, orig: str, expl: str) -> None:
        """Increment the assert counter for test-code assertions only during 'call'."""
        if not self._enabled:
            return
        if self._assertion_frame_is_app_code():
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
        """Copy pre-test lines and arcs into the store as incidental + deliberate (if not already present).

        Lines executed before any test phase (module imports, module-level code,
        bodies of functions called at module level) are recorded in
        ``ctx.pre_test_lines`` by the tracer.  This drains that set into the store
        so reporters see them as covered.  Existing store entries (from call-phase
        tracing) are not overwritten.

        Pre-test lines count as both incidental and deliberate: importing a module
        to run tests is itself a deliberate act, so ``def`` statements and other
        module-level code should not penalise deliberate coverage.
        """
        for key in list(ctx.pre_test_lines):  # snapshot: tracer may still be active
            if key not in store:
                ld = store.get_or_create(key)
                ld.incidental_executions = 1
                ld.deliberate_executions = 1
        ctx.pre_test_lines.clear()
        # Flush pre-test arcs the same way: both incidental and deliberate.
        for arc_key in list(ctx.pre_test_arcs):
            ad = store.get_or_create_arc(arc_key)
            if ad.incidental_executions == 0 and ad.deliberate_executions == 0:
                ad.incidental_executions = 1
                ad.deliberate_executions = 1
        ctx.pre_test_arcs.clear()
