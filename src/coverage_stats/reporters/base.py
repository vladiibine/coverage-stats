from __future__ import annotations

from pathlib import Path
from typing import Protocol

from coverage_stats.reporters.report_data import CoverageReport


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
