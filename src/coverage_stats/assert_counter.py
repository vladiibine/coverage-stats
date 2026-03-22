"""Assert counter module for coverage-stats.

The logic has moved to ProfilerContext.record_assertion() and
ProfilerContext.distribute_asserts(). These module-level functions are kept
for backward compatibility.
"""
from __future__ import annotations

from coverage_stats.profiler import ProfilerContext
from coverage_stats.store import SessionStore


def record_assertion(ctx: ProfilerContext) -> None:
    ctx.record_assertion()


def distribute_asserts(ctx: ProfilerContext, store: SessionStore) -> None:
    ctx.distribute_asserts(store)
