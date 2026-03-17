from __future__ import annotations

import sys
import types
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

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
    current_test_lines: set[tuple[str, int]] = field(default_factory=set)
    # Lines executed before any test phase (module imports, module-level code).
    # Populated when current_phase is None so that module-level statements
    # (including bodies of functions called at import time) are recorded.
    pre_test_lines: set[tuple[str, int]] = field(default_factory=set)


class LineTracer:
    def __init__(self, context: ProfilerContext, store: SessionStore) -> None:
        self._context = context
        self._store = store
        self._prev_trace: _TraceFunc | None = None

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

    def _trace(self, frame: types.FrameType, event: str, arg: Any) -> _TraceFunc:
        """Global trace function, called by Python on every *call* event.

        Forwards the call to the previous global tracer (e.g. coverage.py) and
        captures its return value — the local tracer coverage wants installed for
        this frame.  Returns a per-frame closure that chains both tracers for all
        subsequent events in that frame.
        """
        prev_local: _TraceFunc | None = None
        try:
            if self._prev_trace is not None:
                prev_local = self._prev_trace(frame, event, arg)
        except Exception as exc:
            warnings.warn(f"coverage-stats: tracer error: {exc}")
        return self._make_local_trace(prev_local)

    def _make_local_trace(self, prev_local: _TraceFunc | None) -> _TraceFunc:
        """Return a per-frame local trace function that chains prev_local and our logic.

        ``prev_local`` is whatever the previous global tracer (e.g. coverage.py)
        returned for this frame's *call* event — its own per-frame local tracer.
        We call it first on every event and track its evolving return value so that
        coverage.py can change or cancel its local tracer mid-frame if it needs to.
        """
        current_prev = prev_local

        def local(frame: types.FrameType, event: str, arg: Any) -> _TraceFunc:
            nonlocal current_prev
            try:
                if current_prev is not None:
                    current_prev = current_prev(frame, event, arg)
                if event == "line":
                    ctx = self._context
                    filename = str(Path(frame.f_code.co_filename).resolve())
                    if self._in_scope(filename):
                        lineno = frame.f_lineno
                        key = (filename, lineno)
                        if ctx.current_phase == "call" and ctx.current_test_item is not None:
                            ld = self._store.get_or_create(key)
                            covers_lines: frozenset[tuple[str, int]] = getattr(
                                ctx.current_test_item, "_covers_lines", frozenset()
                            )
                            if key in covers_lines:
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
