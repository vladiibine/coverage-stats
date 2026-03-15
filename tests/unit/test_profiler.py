from __future__ import annotations

import sys
import types
import warnings
from pathlib import Path

import pytest

from coverage_stats.profiler import LineTracer, ProfilerContext
from coverage_stats.store import SessionStore

THIS_FILE = str(Path(__file__).resolve())


def make_frame(filename, lineno):
    code = types.SimpleNamespace(co_filename=filename)
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
        item = types.SimpleNamespace(_covers_lines=frozenset() if covers_lines is None else covers_lines)
        ctx.current_test_item = item
    return tracer, ctx, store


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


def test_stop_restores_previous_trace():
    ctx = ProfilerContext()
    store = SessionStore()
    tracer = LineTracer(ctx, store)
    original = sys.gettrace()
    tracer.start()
    tracer.stop()
    assert sys.gettrace() is original


def test_trace_returns_self_on_call_event():
    tracer, ctx, store = make_tracer()
    frame = make_frame(THIS_FILE, 1)
    result = tracer._trace(frame, "call", None)
    # Bound methods don't have stable identity; compare via __func__ and __self__
    assert result.__func__ is tracer._trace.__func__
    assert result.__self__ is tracer


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

    tracer._trace(frame, "line", None)

    ld = store.get_or_create(key)
    assert ld.deliberate_executions == 1
    assert ld.incidental_executions == 0


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

    tracer._trace(frame, "line", None)

    key = (THIS_FILE, 42)
    ld = store.get_or_create(key)
    assert ld.incidental_executions == 1
    assert ld.deliberate_executions == 0


def test_trace_skips_during_setup_phase():
    tracer, ctx, store = make_tracer(phase="setup")
    frame = make_frame(THIS_FILE, 10)
    tracer._trace(frame, "line", None)
    assert store._data == {}


def test_trace_skips_during_teardown_phase():
    tracer, ctx, store = make_tracer(phase="teardown")
    frame = make_frame(THIS_FILE, 10)
    tracer._trace(frame, "line", None)
    assert store._data == {}


def test_trace_skips_when_no_test_item():
    ctx = ProfilerContext(
        source_dirs=[str(Path(__file__).resolve().parent)],
        current_phase="call",
        current_test_item=None,
    )
    store = SessionStore()
    tracer = LineTracer(ctx, store)
    frame = make_frame(THIS_FILE, 10)
    tracer._trace(frame, "line", None)
    assert store._data == {}


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
    tracer._trace(frame, "line", None)
    assert store._data == {}


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

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tracer._trace(frame, "line", None)

    assert len(caught) == 1
    assert "coverage-stats: tracer error" in str(caught[0].message)


def test_trace_chains_previous_trace():
    ctx = ProfilerContext(
        source_dirs=[str(Path(__file__).resolve().parent)],
        current_phase="call",
    )
    store = SessionStore()
    tracer = LineTracer(ctx, store)

    called = []

    def prev_trace(frame, event, arg):
        called.append(event)
        return None

    tracer._prev_trace = prev_trace

    item = types.SimpleNamespace(_covers_lines=frozenset())
    ctx.current_test_item = item

    frame = make_frame(THIS_FILE, 5)
    tracer._trace(frame, "call", None)
    tracer._trace(frame, "line", None)

    assert "call" in called
    assert "line" in called
