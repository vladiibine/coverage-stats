from __future__ import annotations

import inspect
from typing import Any

from coverage_stats.reporters.base import Reporter


def _instantiate_reporter(cls: type[Reporter], known_kwargs: dict[str, Any]) -> Reporter:
    if cls.__init__ is object.__init__:
        return cls()
    sig = inspect.signature(cls.__init__)
    has_var_keyword = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
    )
    if has_var_keyword:
        return cls(**known_kwargs)
    filtered = {k: v for k, v in known_kwargs.items() if k in sig.parameters}
    return cls(**filtered)


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
