"""
@covers decorator for marking what a test explicitly exercises.

Usage:
    from coverage_stats import covers

    @covers(MyClass.my_method)
    def test_something():
        ...

    @covers(MyClass, "mymodule.some_function")
    def test_multiple():
        ...
"""
from __future__ import annotations

import functools
import inspect
import types
from typing import Any, Callable

# Registry: maps test function qualified name -> list of covered target qualnames.
# Populated at decoration time; test node IDs are resolved at collection time by
# the pytest plugin.
_registry: dict[int, list[str]] = {}  # id(test_func) -> [qualnames]


def _target_to_qualname(target: Any) -> str:
    """Convert a target (callable, class, module, or string) to a dotted qualname."""
    if isinstance(target, str):
        return target
    if isinstance(target, types.ModuleType):
        return target.__name__
    if inspect.isclass(target) or callable(target):
        module = getattr(target, "__module__", None)
        qualname = getattr(target, "__qualname__", None) or getattr(target, "__name__", None)
        if module and qualname:
            return f"{module}.{qualname}"
        if qualname:
            return qualname
    raise TypeError(
        f"@covers targets must be callables, classes, modules, or strings. Got: {type(target)}"
    )


def covers(*targets: Any) -> Callable:
    """
    Decorator that declares what a test explicitly covers.

    The pytest plugin reads this metadata and records it alongside coverage
    context data so the reporter can distinguish direct from incidental hits.
    """
    if not targets:
        raise ValueError("@covers requires at least one target")

    qualnames = [_target_to_qualname(t) for t in targets]

    def decorator(func: Callable) -> Callable:
        _registry[id(func)] = qualnames

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Stash on the wrapper too so the pytest plugin can find it after wrapping.
        _registry[id(wrapper)] = qualnames
        wrapper.__coverage_stats_covers__ = qualnames
        return wrapper

    return decorator


def get_covered_targets(func: Callable) -> list[str] | None:
    """Return the list of covered qualnames for a test function, or None."""
    return getattr(func, "__coverage_stats_covers__", None) or _registry.get(id(func))
