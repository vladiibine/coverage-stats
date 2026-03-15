"""Assert counter module for coverage-stats."""
from __future__ import annotations

from coverage_stats.profiler import ProfilerContext
from coverage_stats.store import SessionStore


def record_assertion(ctx: ProfilerContext) -> None:
    if ctx.current_phase == "call" and ctx.current_test_item is not None:
        ctx.current_assert_count += 1


def distribute_asserts(ctx: ProfilerContext, store: SessionStore) -> None:
    count = ctx.current_assert_count
    if count and ctx.current_test_lines:
        covers_lines: frozenset[tuple[str, int]] = getattr(ctx.current_test_item, "_covers_lines", frozenset())
        for key in ctx.current_test_lines:
            ld = store.get_or_create(key)
            if key in covers_lines:
                ld.deliberate_asserts += count
            else:
                ld.incidental_asserts += count
    ctx.current_assert_count = 0
    ctx.current_test_lines.clear()
