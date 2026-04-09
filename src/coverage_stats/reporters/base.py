from __future__ import annotations

import inspect
from pathlib import Path
from typing import Protocol, runtime_checkable, Any

from coverage_stats.reporters.models import CoverageReport


@runtime_checkable
class Reporter(Protocol):
    """Protocol for coverage-stats reporters.

    A reporter class must implement ``write``. It may also declare known
    constructor parameters — the library will inject matching values when
    instantiating the class. Currently injectable parameters:

    - ``precision: int`` — decimal places for percentage values (default 1)

    Parameters absent from the constructor signature are silently skipped,
    so reporters that don't need a particular option simply omit it.
    Reporters that want to receive all future options may declare ``**kwargs``.
    """

    def write(self, report: CoverageReport, output_dir: Path) -> None: ...


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
