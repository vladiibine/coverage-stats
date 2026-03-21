from __future__ import annotations

import importlib
import inspect
from typing import Any

from coverage_stats.reporters.base import Reporter


def _instantiate_reporter(cls: type, known_kwargs: dict[str, Any]) -> Reporter:
    if cls.__init__ is object.__init__:  # type: ignore[misc]
        return cls()  # type: ignore[return-value]
    sig = inspect.signature(cls.__init__)
    has_var_keyword = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
    )
    if has_var_keyword:
        return cls(**known_kwargs)  # type: ignore[return-value]
    filtered = {k: v for k, v in known_kwargs.items() if k in sig.parameters}
    return cls(**filtered)  # type: ignore[return-value]


def load_reporter_class(dotted_path: str) -> type:
    """Import and return a reporter class from a ``'module.path.ClassName'`` string."""
    module_path, sep, class_name = dotted_path.rpartition(".")
    if not sep:
        raise ValueError(
            f"Invalid reporter path {dotted_path!r}: expected 'module.path.ClassName'"
        )
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not callable(cls):
        raise TypeError(f"{dotted_path!r} is not a callable class")
    return cls  # type: ignore[return-value]


def get_reporter(fmt: str, known_kwargs: dict[str, Any]) -> Reporter | None:
    if fmt == "html":
        from coverage_stats.reporters.html import HtmlReporter
        return _instantiate_reporter(HtmlReporter, known_kwargs)
    if fmt == "json":
        from coverage_stats.reporters.json_reporter import JsonReporter
        return _instantiate_reporter(JsonReporter, known_kwargs)
    if fmt == "csv":
        from coverage_stats.reporters.csv_reporter import CsvReporter
        return _instantiate_reporter(CsvReporter, known_kwargs)
    return None
