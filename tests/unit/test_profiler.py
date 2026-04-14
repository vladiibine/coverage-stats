from __future__ import annotations

import sys
import types
import warnings
from pathlib import Path

from coverage_stats import covers
from coverage_stats.profiler import LineTracer, ProfilerContext
from coverage_stats.tracing_coordinator import TracingCoordinator
from coverage_stats.store import SessionStore

THIS_FILE = str(Path(__file__).resolve())


def make_frame(filename, lineno, co_firstlineno=1):
    code = types.SimpleNamespace(co_filename=filename, co_firstlineno=co_firstlineno)
    return types.SimpleNamespace(f_code=code, f_lineno=lineno)


def make_tracer(source_dirs=None, phase="call", test_item=None, covers_lines=None):
    ctx = ProfilerContext(
        source_dirs=source_dirs or [str(Path(__file__).resolve().parent)],
        current_phase=phase,
        current_test_item=test_item,
    )
    store = SessionStore()
    tracer = LineTracer(ctx, store)
    if test_item is None:
        resolved = frozenset() if covers_lines is None else covers_lines
        item = types.SimpleNamespace(_covers_lines=resolved)
        ctx.current_test_item = item
        ctx.current_covers_lines = resolved  # keep in sync with new field
    return tracer, ctx, store


@covers(LineTracer.start)
def test_start_sets_sys_trace():
    ctx = ProfilerContext()
    store = SessionStore()
    tracer = LineTracer(ctx, store)
    original = sys.gettrace()
    try:
        tracer.start()
        # Bound methods don't have stable identity; compare via __func__ and __self__
        current = sys.gettrace()
        assert current.__func__ is tracer._trace.__func__
        assert current.__self__ is tracer
    finally:
        tracer.stop()
        # Restore original in case test framework had a tracer
        if original is not None:
            sys.settrace(original)


@covers(LineTracer.stop)
def test_stop_restores_previous_trace():
    ctx = ProfilerContext()
    store = SessionStore()
    tracer = LineTracer(ctx, store)
    original = sys.gettrace()
    tracer.start()
    tracer.stop()
    assert sys.gettrace() is original


@covers(LineTracer._trace)
def test_trace_returns_local_closure_on_call_event():
    tracer, ctx, store = make_tracer()
    frame = make_frame(THIS_FILE, 1)
    result = tracer._trace(frame, "call", None)
    # _trace is now a global-only tracer; it returns a per-frame closure, not itself
    assert callable(result)
    assert result is not tracer._trace


@covers(LineTracer._make_local_trace)
def test_trace_accumulates_deliberate_execution():
    frame = make_frame(THIS_FILE, 42)
    source_dirs = [str(Path(__file__).resolve().parent)]
    ctx = ProfilerContext(
        source_dirs=source_dirs,
        current_phase="call",
    )
    store = SessionStore()
    tracer = LineTracer(ctx, store)

    key = (THIS_FILE, 42)
    item = types.SimpleNamespace(_covers_lines=frozenset([key]))
    ctx.current_test_item = item
    ctx.current_covers_lines = frozenset([key])

    local = tracer._trace(frame, "call", None)
    local(frame, "line", None)

    ld = store.get_or_create(key)
    assert ld.deliberate_executions == 1
    assert ld.incidental_executions == 0


@covers(LineTracer._make_local_trace)
def test_trace_accumulates_incidental_execution():
    frame = make_frame(THIS_FILE, 42)
    source_dirs = [str(Path(__file__).resolve().parent)]
    ctx = ProfilerContext(
        source_dirs=source_dirs,
        current_phase="call",
    )
    store = SessionStore()
    tracer = LineTracer(ctx, store)

    item = types.SimpleNamespace(_covers_lines=frozenset())
    ctx.current_test_item = item

    local = tracer._trace(frame, "call", None)
    local(frame, "line", None)

    key = (THIS_FILE, 42)
    ld = store.get_or_create(key)
    assert ld.incidental_executions == 1
    assert ld.deliberate_executions == 0


@covers(LineTracer._make_local_trace)
def test_trace_skips_during_setup_phase():
    tracer, ctx, store = make_tracer(phase="setup")
    frame = make_frame(THIS_FILE, 10)
    local = tracer._trace(frame, "call", None)
    local(frame, "line", None)
    assert store._data == {}


@covers(LineTracer._make_local_trace)
def test_trace_skips_during_teardown_phase():
    tracer, ctx, store = make_tracer(phase="teardown")
    frame = make_frame(THIS_FILE, 10)
    local = tracer._trace(frame, "call", None)
    local(frame, "line", None)
    assert store._data == {}


@covers(LineTracer._make_local_trace)
def test_trace_skips_when_no_test_item():
    ctx = ProfilerContext(
        source_dirs=[str(Path(__file__).resolve().parent)],
        current_phase="call",
        current_test_item=None,
    )
    store = SessionStore()
    tracer = LineTracer(ctx, store)
    frame = make_frame(THIS_FILE, 10)
    local = tracer._trace(frame, "call", None)
    local(frame, "line", None)
    assert store._data == {}


@covers(LineTracer._in_scope)
def test_trace_skips_file_outside_source_dirs():
    ctx = ProfilerContext(
        source_dirs=["/other/path"],
        current_phase="call",
    )
    store = SessionStore()
    tracer = LineTracer(ctx, store)
    item = types.SimpleNamespace(_covers_lines=frozenset())
    ctx.current_test_item = item

    frame = make_frame("/my/src/foo.py", 5)
    # Out-of-scope frames return None so Python won't call us for line events
    result = tracer._trace(frame, "call", None)
    assert result is None
    assert store._data == {}


@covers(LineTracer._make_local_trace)
def test_trace_catches_exception_and_warns():
    class BrokenStore:
        def get_or_create(self, key):
            raise RuntimeError("boom")

    ctx = ProfilerContext(
        source_dirs=[str(Path(__file__).resolve().parent)],
        current_phase="call",
    )
    store = BrokenStore()
    tracer = LineTracer(ctx, store)
    item = types.SimpleNamespace(_covers_lines=frozenset())
    ctx.current_test_item = item

    frame = make_frame(THIS_FILE, 99)
    local = tracer._trace(frame, "call", None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        local(frame, "line", None)

    assert len(caught) == 1
    assert "coverage-stats: tracer error" in str(caught[0].message)


@covers(LineTracer._trace)
def test_trace_forwards_call_to_prev_global_tracer():
    """The previous global tracer must be called with the 'call' event."""
    ctx = ProfilerContext(
        source_dirs=[str(Path(__file__).resolve().parent)],
        current_phase="call",
    )
    store = SessionStore()
    tracer = LineTracer(ctx, store)

    global_called = []

    def prev_trace(frame, event, arg):
        global_called.append(event)
        return None  # no local tracer

    tracer._prev_trace = prev_trace
    frame = make_frame(THIS_FILE, 5)
    tracer._trace(frame, "call", None)

    assert global_called == ["call"]


@covers(LineTracer._make_local_trace)
def test_trace_uses_local_tracer_returned_by_prev_global_tracer():
    """If the previous global tracer returns a local tracer, that local must be
    called on subsequent line events — not the global tracer itself."""
    ctx = ProfilerContext(
        source_dirs=[str(Path(__file__).resolve().parent)],
        current_phase="call",
    )
    store = SessionStore()
    tracer = LineTracer(ctx, store)

    local_events: list[str] = []
    global_events: list[str] = []

    def prev_local(frame, event, arg):
        local_events.append(event)
        return prev_local

    def prev_trace(frame, event, arg):
        global_events.append(event)
        return prev_local  # return a distinct local tracer

    tracer._prev_trace = prev_trace
    item = types.SimpleNamespace(_covers_lines=frozenset())
    ctx.current_test_item = item

    frame = make_frame(THIS_FILE, 5)
    local = tracer._trace(frame, "call", None)
    local(frame, "line", None)

    assert global_events == ["call"]       # global only sees call
    assert "line" in local_events          # local sees line, not global
    assert "line" not in global_events


# ---------------------------------------------------------------------------
# _flush_pre_test_lines tests
# ---------------------------------------------------------------------------


@covers(TracingCoordinator.flush_pre_test_lines)
def test_flush_pre_test_lines_sets_both_incidental_and_deliberate():
    """Pre-test lines not yet in the store should be marked as both incidental
    and deliberate: importing a module to run tests is itself a deliberate act."""
    ctx = ProfilerContext(source_dirs=[])
    ctx.pre_test_lines = {("src/foo.py", 1)}
    store = SessionStore()
    TracingCoordinator.flush_pre_test_lines(ctx, store)
    ld = store._data[("src/foo.py", 1)]
    assert ld.incidental_executions == 1
    assert ld.deliberate_executions == 1


@covers(TracingCoordinator.flush_pre_test_lines)
def test_flush_pre_test_lines_does_not_overwrite_existing_store_entry():
    """If a line already has call-phase data in the store, the flush must not
    clobber it."""
    ctx = ProfilerContext(source_dirs=[])
    ctx.pre_test_lines = {("src/foo.py", 2)}
    store = SessionStore()
    ld = store.get_or_create(("src/foo.py", 2))
    ld.deliberate_executions = 3
    ld.incidental_executions = 5
    TracingCoordinator.flush_pre_test_lines(ctx, store)
    assert store._data[("src/foo.py", 2)].deliberate_executions == 3
    assert store._data[("src/foo.py", 2)].incidental_executions == 5


@covers(TracingCoordinator.flush_pre_test_lines)
def test_flush_pre_test_lines_clears_pre_test_set():
    ctx = ProfilerContext(source_dirs=[])
    ctx.pre_test_lines = {("src/foo.py", 1), ("src/foo.py", 2)}
    store = SessionStore()
    TracingCoordinator.flush_pre_test_lines(ctx, store)
    assert ctx.pre_test_lines == set()
