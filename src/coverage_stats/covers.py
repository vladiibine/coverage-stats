from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest


class CoverageStatsError(Exception):
    pass


class CoverageStatsResolutionError(CoverageStatsError):
    pass


def covers(*refs: Any) -> Any:
    """Decorator that marks which functions/classes a test deliberately covers.

    String refs are resolved lazily at pytest_runtest_setup.
    Object refs are already evaluated at decoration time.
    """
    if not refs:
        raise TypeError("@covers requires at least one argument")

    def decorator(fn: Any) -> Any:
        fn._covers_refs = refs
        return fn

    return decorator


def resolve_covers(item: Any) -> None:
    """Resolve @covers refs on a pytest item and store on item._covers_lines.

    Called from pytest_runtest_setup. Stores frozenset[tuple[str, int]] on
    item._covers_lines. Sets empty frozenset if no @covers decorator present.
    """
    refs = getattr(item.function, "_covers_refs", None)
    if refs is None and item.cls is not None:
        refs = getattr(item.cls, "_covers_refs", None)
    if not refs:
        item._covers_lines = frozenset()
        return

    lines: set[tuple[str, int]] = set()
    for ref in refs:
        lines.update(_resolve_ref(ref, item))

    item._covers_lines = frozenset(lines)


def _resolve_ref(ref: Any, item: Any) -> set[tuple[str, int]]:
    """Resolve a single ref (string or object) to a set of (abs_path, lineno) tuples."""
    if isinstance(ref, str):
        target = _resolve_dotted_string(ref, item)
    else:
        target = ref
    return _get_source_lines(target, ref, item)


def _resolve_dotted_string(ref: str, item: Any) -> Any:
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


def _get_source_lines(target: Any, ref: Any, item: Any) -> set[tuple[str, int]]:
    """Return all (abs_path, lineno) pairs in target's source."""
    if inspect.isclass(target):
        return _get_class_lines(target, ref, item)
    elif inspect.isfunction(target) or inspect.ismethod(target):
        return _get_callable_lines(target, ref, item)
    else:
        pytest.fail(
            f"coverage-stats: cannot resolve @covers target {repr(ref)} "
            f"for test {item.nodeid} — not a function or class: {type(target)!r}"
        )


def _get_callable_lines(target: Any, ref: Any, item: Any) -> set[tuple[str, int]]:
    src_file = inspect.getsourcefile(target)
    if src_file is None:
        pytest.fail(
            f"coverage-stats: cannot resolve @covers target {repr(ref)} "
            f"for test {item.nodeid} — getsourcefile returned None (built-in or C extension?)"
        )
    abs_path = str(Path(src_file).resolve())
    source_lines, start_lineno = inspect.getsourcelines(target)
    return {(abs_path, start_lineno + i) for i in range(len(source_lines))}


def _get_class_lines(target: Any, ref: Any, item: Any) -> set[tuple[str, int]]:
    lines = _get_callable_lines(target, ref, item)
    for _name, method in inspect.getmembers(target, predicate=inspect.isfunction):
        lines = lines | _get_callable_lines(method, ref, item)
    return lines
