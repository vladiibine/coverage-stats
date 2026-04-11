from __future__ import annotations

import sys
import types
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    import pytest
    from coverage_stats.store import SessionStore

# sys.settrace expects Callable[[FrameType, str, Any], TraceFunction | None].
# Using Any for arg and return keeps this compatible with typeshed's TraceFunction.
_TraceFunc = Callable[[types.FrameType, str, Any], Any]


@dataclass
class ProfilerContext:
    current_test_item: pytest.Item | None = None
    current_phase: str | None = None  # "setup" | "call" | "teardown"
    current_assert_count: int = 0
    source_dirs: list[str] = field(default_factory=list)
    exclude_dirs: list[str] = field(default_factory=list)
    # Holds the sys.meta_path ensurer registered during pytest_load_initial_conftests
    # so TracingCoordinator can remove it once conftest loading is done.
    meta_path_ensurer: Optional[Any] = field(default=None, repr=False)
    current_test_lines: set[tuple[str, int]] = field(default_factory=set)
    # Lines executed before any test phase (module imports, module-level code).
    # Populated when current_phase is None so that module-level statements
    # (including bodies of functions called at import time) are recorded.
    pre_test_lines: set[tuple[str, int]] = field(default_factory=set)
    # Resolved @covers lines for the current test, set once in pytest_runtest_setup
    # and read on every line event.  Storing it here avoids a getattr() on every
    # line event in the tracer hot path.
    current_covers_lines: frozenset[tuple[str, int]] = field(default_factory=frozenset)
    # When True (the default), distribute_asserts records the test node ID string
    # in LineData.  Set to False via --coverage-stats-no-track-test-ids to reduce
    # memory usage at the cost of losing per-line test attribution.
    track_test_ids: bool = True

    def record_assertion(self) -> None:
        """Increment the assert counter when an assertion passes during the call phase."""
        if self.current_phase == "call" and self.current_test_item is not None:
            self.current_assert_count += 1

    def distribute_asserts(self, store: SessionStore) -> None:
        """Distribute accumulated assert count to every line executed this test, then reset."""
        covers_lines = self.current_covers_lines
        count = self.current_assert_count
        nodeid: str | None = (
            self.current_test_item.nodeid
            if self.track_test_ids and self.current_test_item is not None
            else None
        )
        for key in self.current_test_lines:
            ld = store.get_or_create(key)
            if key in covers_lines:
                if count:
                    ld.deliberate_asserts += count
                ld.deliberate_tests += 1
                if nodeid is not None:
                    ld.deliberate_test_ids.add(nodeid)
            else:
                if count:
                    ld.incidental_asserts += count
                ld.incidental_tests += 1
                if nodeid is not None:
                    ld.incidental_test_ids.add(nodeid)
        self.current_assert_count = 0
        self.current_test_lines.clear()


class MonitoringLineTracer:
    """Line tracer using sys.monitoring (Python 3.12+).

    Registers for LINE events via sys.monitoring, which avoids the sys.settrace
    single-slot constraint entirely.  Multiple monitoring tools can coexist
    without chaining or displacement — coverage.py registers via COVERAGE_ID (1)
    while we claim a separate tool ID.

    start() is idempotent: if our tool ID is already registered, it returns
    immediately without re-registering.
    """

    def __init__(self, context: ProfilerContext, store: SessionStore) -> None:
        self._context = context
        self._store = store
        self._tool_id: int | None = None
        self._scope_cache: dict[str, tuple[str, bool]] = {}
        # Precompute (exact, prefix/) pairs once so _in_scope avoids allocating
        # `d + "/"` on every call.
        self._source_prefixes: list[tuple[str, str]] = [
            (d, d + "/") for d in context.source_dirs
        ]
        self._exclude_prefixes: list[tuple[str, str]] = [
            (d, d + "/") for d in context.exclude_dirs
        ]

    def start(self) -> None:
        if self._tool_id is not None:
            return  # already running — idempotent, no displacement possible
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            warnings.warn("coverage-stats: sys.monitoring not available (requires Python 3.12+)")
            return
        # Tool IDs 0-3 are reserved for standard tools (debugger, coverage,
        # profiler, optimizer).  We try IDs 4 and 5 first, then fall back.
        for tool_id in (4, 5, 3, 2):
            try:
                monitoring.use_tool_id(tool_id, "coverage-stats")
                self._tool_id = tool_id
                break
            except ValueError:
                continue
        if self._tool_id is None:
            warnings.warn("coverage-stats: no sys.monitoring tool ID available, line tracing disabled")
            return
        monitoring.set_events(self._tool_id, monitoring.events.LINE)
        monitoring.register_callback(self._tool_id, monitoring.events.LINE, self._monitoring_line)

    def stop(self) -> None:
        if self._tool_id is None:
            return
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            return
        monitoring.set_events(self._tool_id, monitoring.events.NO_EVENTS)
        monitoring.register_callback(self._tool_id, monitoring.events.LINE, None)
        monitoring.free_tool_id(self._tool_id)
        self._tool_id = None

    def _in_scope(self, filename: str) -> bool:
        if "site-packages" in filename:
            return False
        if self._exclude_prefixes and any(
            filename == d or filename.startswith(p) for d, p in self._exclude_prefixes
        ):
            return False
        if self._source_prefixes:
            return any(filename == d or filename.startswith(p) for d, p in self._source_prefixes)
        return True

    def _monitoring_line(self, code: types.CodeType, line_number: int) -> object:
        """Callback invoked by sys.monitoring for every LINE event.

        Returns sys.monitoring.DISABLE for out-of-scope code objects so Python
        stops calling us for every line in those files — same optimisation that
        LineTracer achieves by returning None from the global trace function.
        """
        raw = code.co_filename
        cached = self._scope_cache.get(raw)
        if cached is None:
            if raw.startswith("<"):
                self._scope_cache[raw] = (raw, False)
                return sys.monitoring.DISABLE  # type: ignore[attr-defined]
            filename = str(Path(raw).resolve())
            in_scope = self._in_scope(filename)
            self._scope_cache[raw] = (filename, in_scope)
        else:
            filename, in_scope = cached

        if not in_scope:
            return sys.monitoring.DISABLE  # type: ignore[attr-defined]

        ctx = self._context
        key = (filename, line_number)
        if ctx.current_phase == "call" and ctx.current_test_item is not None:
            ld = self._store.get_or_create(key)
            if key in ctx.current_covers_lines:
                ld.deliberate_executions += 1
            else:
                ld.incidental_executions += 1
            ctx.current_test_lines.add(key)
        elif ctx.current_phase is None:
            ctx.pre_test_lines.add(key)
        return None


# TODO - document that this tracer uses sys.settrace, whereas the other one uses sys.monitoring
#  Also, rename the tracers more appropriately in line with their roles
class LineTracer:
    def __init__(self, context: ProfilerContext, store: SessionStore) -> None:
        self._context = context
        self._store = store
        self._prev_trace: _TraceFunc | None = None
        # When the previous tracer is a C extension (e.g. coverage.py's CTracer
        # on Python < 3.12), chaining to it is unsafe: calling it directly from
        # Python code triggers its self-healing behaviour (it calls
        # sys.settrace(self) as a side effect), creating an endless reinstall
        # battle that prevents both tracers from working.  We detect this case
        # once in start() and skip chaining for the rest of the session.
        self._skip_prev_trace: bool = False
        # The bound-method object actually passed to sys.settrace, stored so we
        # can detect whether we're still on top without creating a new bound
        # method via self._trace (which would fail an `is` comparison).
        self._installed_fn: _TraceFunc | None = None
        # Cache raw co_filename → (resolved_str, in_scope) so _trace pays the
        # Path.resolve() + _in_scope cost at most once per unique source file.
        self._scope_cache: dict[str, tuple[str, bool]] = {}
        # Precompute (exact, prefix/) pairs once so _in_scope avoids allocating
        # `d + "/"` on every call.
        self._source_prefixes: list[tuple[str, str]] = [
            (d, d + "/") for d in context.source_dirs
        ]
        self._exclude_prefixes: list[tuple[str, str]] = [
            (d, d + "/") for d in context.exclude_dirs
        ]

    def start(self) -> None:
        current = sys.gettrace()
        if self._installed_fn is not None and current is self._installed_fn:
            # Already on top and not displaced by another tracer — nothing to do.
            # This happens on Python 3.12+ where coverage.py uses sys.monitoring
            # and never calls sys.settrace, so our first install from
            # pytest_sessionstart is still in place when pytest_collection_finish
            # calls start() again.
            return
        self._prev_trace = current
        self._skip_prev_trace = self._is_c_extension_tracer(self._prev_trace)
        self._installed_fn = self._trace
        sys.settrace(self._installed_fn)

    def stop(self) -> None:
        sys.settrace(self._prev_trace)

    def _in_scope(self, filename: str) -> bool:
        if "site-packages" in filename:
            return False
        if self._exclude_prefixes and any(
            filename == d or filename.startswith(p) for d, p in self._exclude_prefixes
        ):
            return False
        if self._source_prefixes:
            return any(filename == d or filename.startswith(p) for d, p in self._source_prefixes)
        return True

    def _trace(self, frame: types.FrameType, event: str, arg: Any) -> _TraceFunc:
        """Global trace function, called by Python on every *call* event.

        Resolves the filename once per frame and decides up-front whether this
        frame needs line-level tracking.  For out-of-scope frames we return either
        ``None`` (no previous tracer) or a minimal wrapper that only forwards to
        the previous tracer — this prevents Python from calling us on every line
        event inside those frames, which was the dominant source of overhead.
        """
        # Resolve the filename once per unique co_filename (cached).
        raw = frame.f_code.co_filename
        cached = self._scope_cache.get(raw)
        if cached is None:
            if raw.startswith("<"):
                self._scope_cache[raw] = (raw, False)
                return None  # type: ignore[return-value]
            filename = str(Path(raw).resolve())
            in_scope = self._in_scope(filename)
            self._scope_cache[raw] = (filename, in_scope)
        else:
            filename, in_scope = cached

        prev_local: _TraceFunc | None = None
        if not self._skip_prev_trace:
            try:
                if self._prev_trace is not None:
                    prev_local = self._prev_trace(frame, event, arg)
            except Exception as exc:
                warnings.warn(f"coverage-stats: tracer error: {exc}")

        if not in_scope:
            # Out-of-scope frame: don't install our line handler.
            # If there's a previous tracer (e.g. a Python-level debugger), return
            # a thin wrapper that only forwards to it so it keeps working.
            if prev_local is None:
                return None  # type: ignore[return-value]
            return self._make_forwarding_trace(prev_local)

        return self._make_local_trace(filename, prev_local)

    def _make_forwarding_trace(self, prev_local: _TraceFunc) -> _TraceFunc:
        """Minimal local tracer for out-of-scope frames that only chains prev_local."""
        current_prev = prev_local

        def forward(frame: types.FrameType, event: str, arg: Any) -> _TraceFunc:
            nonlocal current_prev
            try:
                current_prev = current_prev(frame, event, arg)
            except Exception as exc:
                warnings.warn(f"coverage-stats: tracer error: {exc}")
            if current_prev is None:
                return None
            return forward

        return forward

    def _make_local_trace(self, filename: str, prev_local: _TraceFunc | None) -> _TraceFunc:
        """Return a per-frame local trace function for an in-scope frame.

        The filename is already resolved and known to be in scope — no repeated
        path work on every line event.  prev_local is a Python-level local tracer
        for this frame (if any); we chain it so other tools keep working.

        ctx and store are captured once as closure locals so the hot path avoids
        repeated LOAD_ATTR on self.  Python calls local trace functions only for
        "line", "return", and "exception" events; we handle "line" by position
        (frame.f_lineno) and let the other two pass through cheaply.
        """
        ctx = self._context  # captured once — avoids LOAD_ATTR on self per call
        store = self._store  # captured once — avoids LOAD_ATTR on self per call
        current_prev = prev_local

        def local(frame: types.FrameType, event: str, arg: Any) -> _TraceFunc:
            nonlocal current_prev
            try:
                if current_prev is not None:
                    current_prev = current_prev(frame, event, arg)
                if event == "line":
                    lineno = frame.f_lineno
                    key = (filename, lineno)
                    if ctx.current_phase == "call" and ctx.current_test_item is not None:
                        ld = store.get_or_create(key)
                        if key in ctx.current_covers_lines:
                            ld.deliberate_executions += 1
                        else:
                            ld.incidental_executions += 1
                        ctx.current_test_lines.add(key)
                    elif ctx.current_phase is None:
                        ctx.pre_test_lines.add(key)
            except Exception as exc:
                warnings.warn(f"coverage-stats: tracer error: {exc}")
            return local

        return local

    def _is_c_extension_tracer(self, func: Any) -> bool:
        """Return True if *func* is a C extension callable.

        C extension trace functions (e.g. coverage.py's CTracer) have a
        self-healing behaviour: when called directly from Python code (not via
        Python's internal C-level trace dispatch) they call sys.settrace(self) as
        a side effect, overwriting whatever tracer was on top of them.  Calling
        such a function from within our own trace dispatch therefore starts an
        endless reinstall battle.  We detect them by checking that they are
        callable but are not plain Python functions or bound methods.
        """
        if func is None:
            return False
        if isinstance(func, (types.FunctionType, types.MethodType)):
            return False
        return callable(func)

