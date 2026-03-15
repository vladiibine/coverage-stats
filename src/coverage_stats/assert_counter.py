"""Assert counter module for coverage-stats."""
from __future__ import annotations

from coverage_stats.profiler import ProfilerContext


def handle_assertion_pass(context: ProfilerContext) -> None:
    raise NotImplementedError
