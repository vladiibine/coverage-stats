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

    def record_assertion(self) -> None:
        """Increment the assert counter when an assertion passes during the call phase."""
        if self.current_phase == "call" and self.current_test_item is not None:
            self.current_assert_count += 1

    def distribute_asserts(self, store: SessionStore) -> None:
        """Distribute accumulated assert count to every line executed this test, then reset."""
        covers_lines: frozenset[tuple[str, int]] = getattr(
            self.current_test_item, "_covers_lines", frozenset()
        )
        count = self.current_assert_count
        for key in self.current_test_lines:
            ld = store.get_or_create(key)
            if key in covers_lines:
                if count:
                    ld.deliberate_asserts += count
                ld.deliberate_tests += 1
            else:
                if count:
                    ld.incidental_asserts += count
                ld.incidental_tests += 1
        self.current_assert_count = 0
        self.current_test_lines.clear()


class LineTracer:
    def __init__(self, context: ProfilerContext, store: SessionStore) -> None:
        self._context = context
        self._store = store
        self._prev_trace: _TraceFunc | None = None
        # Cache raw co_filename → (resolved_str, in_scope) so _trace pays the
        # Path.resolve() + _in_scope cost at most once per unique source file.
        self._scope_cache: dict[str, tuple[str, bool]] = {}

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
            filename = str(Path(raw).resolve())
            in_scope = self._in_scope(filename)
            self._scope_cache[raw] = (filename, in_scope)
        else:
            filename, in_scope = cached

        prev_local: _TraceFunc | None = None
        try:
            if self._prev_trace is not None:
                prev_local = self._prev_trace(frame, event, arg)
        except Exception as exc:
            warnings.warn(f"coverage-stats: tracer error: {exc}")

        if not in_scope:
            # Out-of-scope frame: don't install our line handler.
            # If there's a previous tracer (e.g. coverage.py), return a thin
            # wrapper that only forwards to it so coverage.py keeps working.
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
        path work on every line event.  prev_local is coverage.py's local tracer
        for this frame (if any); we chain it so coverage.py keeps working.
        """
        current_prev = prev_local

        def local(frame: types.FrameType, event: str, arg: Any) -> _TraceFunc:
            nonlocal current_prev
            try:
                if current_prev is not None:
                    current_prev = current_prev(frame, event, arg)
                if event == "line":
                    ctx = self._context
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
