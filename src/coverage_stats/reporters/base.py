from __future__ import annotations

from pathlib import Path
from typing import Protocol

from coverage_stats.reporters.report_data import CoverageReport


class Reporter(Protocol):
    def write(self, report: CoverageReport, output_dir: Path) -> None: ...
