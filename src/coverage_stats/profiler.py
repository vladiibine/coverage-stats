from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProfilerContext:
    current_test_item: Any | None = None
    current_phase: str | None = None  # "setup" | "call" | "teardown"
    current_assert_count: int = 0
    source_dirs: list[str] = field(default_factory=list)


class LineTracer:
    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def _trace(self, frame, event, arg):
        raise NotImplementedError
