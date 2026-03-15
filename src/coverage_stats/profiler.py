from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProfilerContext:
    current_test_item: Any | None = None
    current_phase: str | None = None  # "setup" | "call" | "teardown"
    current_assert_count: int = 0
    source_dirs: list[str] = field(default_factory=list)


class LineTracer:
    def __init__(self, context: ProfilerContext, store: Any) -> None:
        self._context = context
        self._store = store
        self._prev_trace: Any = None

    def start(self) -> None:
        self._prev_trace = sys.gettrace()
        sys.settrace(self._trace)

    def stop(self) -> None:
        sys.settrace(self._prev_trace)

    def _in_scope(self, filename: str) -> bool:
        if self._context.source_dirs:
            return any(
                filename == d or filename.startswith(d + "/")
                for d in self._context.source_dirs
            )
        prefix = sys.prefix if sys.prefix.endswith("/") else sys.prefix + "/"
        return "site-packages" not in filename and not filename.startswith(prefix)

    def _trace(self, frame: Any, event: str, arg: Any) -> Any:
        try:
            if self._prev_trace is not None:
                self._prev_trace(frame, event, arg)
            if event == "call":
                return self._trace
            if event != "line":
                return None
            ctx = self._context
            if ctx.current_phase != "call" or ctx.current_test_item is None:
                return None
            filename = str(Path(frame.f_code.co_filename).resolve())
            if not self._in_scope(filename):
                return None
            lineno = frame.f_lineno
            key = (filename, lineno)
            ld = self._store.get_or_create(key)
            covers_lines = getattr(ctx.current_test_item, "_covers_lines", frozenset())
            if key in covers_lines:
                ld.deliberate_executions += 1
            else:
                ld.incidental_executions += 1
        except Exception as exc:
            warnings.warn(f"coverage-stats: tracer error: {exc}")
        return self._trace
