"""Benchmarks for the tracer hot-path.

Run with:
    nox -s benchmark
"""
from __future__ import annotations

import sys

import pytest

from coverage_stats.profiler import LineTracer, ProfilerContext
from coverage_stats.store import SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeItem:
    """Minimal stand-in for pytest.Item — only its identity matters."""


class _FakeFrame:
    """Minimal frame-like object; the local trace function only reads f_lineno."""
    f_lineno: int = 10


# ---------------------------------------------------------------------------
# LineTracer (sys.settrace, Python 3.9+)
# ---------------------------------------------------------------------------


@pytest.fixture
def tracer_in_scope():
    """Return a (local_trace_fn, store) pair configured for the call phase."""
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=["/src"])
    ctx.current_phase = "call"
    ctx.current_test_item = _FakeItem()  # type: ignore[assignment]
    ctx.current_covers_lines = frozenset()
    tracer = LineTracer(ctx, store)
    local = tracer._make_local_trace("/src/module.py", None)
    return local, store


def test_line_tracer_in_scope_call_phase(benchmark, tracer_in_scope):
    """Local trace function for an in-scope file during the call phase.

    This is the dominant hot path: every executed line in a tracked source
    file triggers this closure.  Measures calls/second.
    """
    local, _store = tracer_in_scope
    frame = _FakeFrame()

    def run():
        for _ in range(10_000):
            local(frame, "line", None)

    benchmark(run)


def test_line_tracer_non_line_event(benchmark, tracer_in_scope):
    """Local trace function for non-line events (return / exception).

    These should be extremely cheap — the closure checks event == "line"
    first and skips all store work for other event types.
    """
    local, _store = tracer_in_scope
    frame = _FakeFrame()

    def run():
        for _ in range(10_000):
            local(frame, "return", None)

    benchmark(run)


def test_line_tracer_scope_cache_hit(benchmark):
    """Local trace function after the scope cache is already warm.

    Exercises only the store write and context update — no path resolution.
    All other tests pre-warm the cache via _make_local_trace; this makes the
    isolation explicit.
    """
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=["/src"])
    ctx.current_phase = "call"
    ctx.current_test_item = _FakeItem()  # type: ignore[assignment]
    ctx.current_covers_lines = frozenset()
    tracer = LineTracer(ctx, store)

    # Scope cache already warm: _make_local_trace has the resolved filename.
    tracer._scope_cache["/src/module.py"] = ("/src/module.py", True)
    local = tracer._make_local_trace("/src/module.py", None)
    frame = _FakeFrame()

    def run():
        for _ in range(10_000):
            local(frame, "line", None)

    benchmark(run)


# ---------------------------------------------------------------------------
# MonitoringLineTracer (sys.monitoring, Python 3.12+)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.version_info < (3, 12), reason="sys.monitoring requires Python 3.12+")
def test_monitoring_line_tracer_in_scope(benchmark):
    """_monitoring_line callback for an in-scope file during the call phase."""
    from coverage_stats.profiler import MonitoringLineTracer

    store = SessionStore()
    ctx = ProfilerContext(source_dirs=["/src"])
    ctx.current_phase = "call"
    ctx.current_test_item = _FakeItem()  # type: ignore[assignment]
    ctx.current_covers_lines = frozenset()
    tracer = MonitoringLineTracer(ctx, store)

    # Warm the scope cache so the benchmark measures only the hot path.
    tracer._scope_cache["<benchmark>"] = ("/src/module.py", True)

    # Create a minimal code object whose co_filename matches the cache key.
    code = compile("x = 1", "<benchmark>", "exec")

    def run():
        for lineno in range(10_000):
            tracer._monitoring_line(code, lineno % 100 + 1)

    benchmark(run)
