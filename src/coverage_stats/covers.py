from __future__ import annotations

import importlib
import inspect
import types
from pathlib import Path
from typing import Any, Callable, TypeVar, Union

import pytest

from coverage_stats.executable_lines import ExecutableLinesAnalyzer


class CoverageStatsError(Exception):
    pass


class CoverageStatsResolutionError(CoverageStatsError):
    pass


_F = TypeVar("_F")

# Types accepted by inspect.getsourcefile / inspect.getsourcelines
# Union[] is needed for python 3.9
_InspectTarget = Union[type[object], types.FunctionType, types.MethodType]


def covers(*refs: object) -> Callable[[_F], _F]:
    """Decorator that marks which functions/classes a test deliberately covers.

    String refs are resolved lazily at pytest_runtest_setup.
    Object refs are already evaluated at decoration time.
    """
    if not refs:
        raise TypeError("@covers requires at least one argument")

    def decorator(fn: _F) -> _F:
        setattr(fn, "_covers_refs", refs)
        return fn

    return decorator


class CoverageStatsResolver:
    """Resolves ``@covers`` references to ``(file, lineno)`` sets.

    Called from ``TracingCoordinator.pytest_runtest_setup`` for each test item.
    Override methods to customise how refs are resolved or how source lines
    are determined.
    """

    def __init__(self, analyzer: ExecutableLinesAnalyzer | None = None) -> None:
        self._analyzer = analyzer if analyzer is not None else ExecutableLinesAnalyzer()

    def resolve_covers(self, item: pytest.Function) -> None:
        """Resolve @covers refs on a pytest item and store on item._covers_lines.

        Stores frozenset[tuple[str, int]] on item._covers_lines.
        Sets empty frozenset if no @covers decorator is present.
        """
        refs = getattr(item.function, "_covers_refs", None)
        if refs is None and item.cls is not None:
            refs = getattr(item.cls, "_covers_refs", None)
        if not refs:
            item._covers_lines = frozenset()  # type: ignore[attr-defined]
            return

        lines: set[tuple[str, int]] = set()
        for ref in refs:
            lines.update(self._resolve_ref(ref, item))

        item._covers_lines = frozenset(lines)  # type: ignore[attr-defined]

    def _resolve_ref(self, ref: object, item: pytest.Function) -> set[tuple[str, int]]:
        """Resolve a single ref (string or object) to a set of (abs_path, lineno) tuples."""
        if isinstance(ref, str):
            target = self._resolve_dotted_string(ref, item)
        else:
            target = ref
        return self._get_source_lines(target, ref, item)

    def _resolve_dotted_string(self, ref: str, item: pytest.Function) -> object:
        """Resolve a dotted string ref by trying longest module prefix first."""
        parts = ref.split(".")
        for i in range(len(parts), 0, -1):
            try:
                module = importlib.import_module(".".join(parts[:i]))
                obj: Any = module
                for attr in parts[i:]:
                    obj = getattr(obj, attr)
                return obj
            except ImportError:
                continue
            except AttributeError as exc:
                pytest.fail(
                    f"coverage-stats: cannot resolve @covers target {repr(ref)} "
                    f"for test {item.nodeid} — {exc}"
                )
        pytest.fail(
            f"coverage-stats: cannot resolve @covers target {repr(ref)} "
            f"for test {item.nodeid} — no importable module prefix found"
        )

    def _get_source_lines(self, target: object, ref: object, item: pytest.Function) -> set[tuple[str, int]]:
        """Return all (abs_path, lineno) pairs in target's source."""
        if inspect.isclass(target):
            return self._get_class_lines(target, ref, item)
        elif inspect.isfunction(target) or inspect.ismethod(target):
            return self._get_callable_lines(target, ref, item)
        else:
            pytest.fail(
                f"coverage-stats: cannot resolve @covers target {repr(ref)} "
                f"for test {item.nodeid} — not a function or class: {type(target)!r}"
            )
            return set()  # unreachable; pytest.fail always raises

    def _get_callable_lines(self, target: _InspectTarget, ref: object, item: pytest.Function) -> set[tuple[str, int]]:
        src_file = inspect.getsourcefile(target)
        if src_file is None:
            pytest.fail(
                f"coverage-stats: cannot resolve @covers target {repr(ref)} "
                f"for test {item.nodeid} — getsourcefile returned None (built-in or C extension?)"
            )
            return set()  # unreachable; pytest.fail always raises
        abs_path = str(Path(src_file).resolve())
        source_lines, start_lineno = inspect.getsourcelines(target)
        executable = self._analyzer.get_executable_lines(abs_path)
        all_linenos = {start_lineno + i for i in range(len(source_lines))}
        # Keep only executable statements; fall back to all lines if analysis failed
        filtered = all_linenos & executable if executable else all_linenos
        return {(abs_path, lineno) for lineno in filtered}

    def _get_class_lines(self, target: type[object], ref: object, item: pytest.Function) -> set[tuple[str, int]]:
        lines = self._get_callable_lines(target, ref, item)
        for _name, method in inspect.getmembers(target, predicate=inspect.isfunction):
            try:
                lines = lines | self._get_callable_lines(method, ref, item)
            except OSError:
                pass  # skip generated methods (e.g. dataclass __eq__) with no source
        return lines
