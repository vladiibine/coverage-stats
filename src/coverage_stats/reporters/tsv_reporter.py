from __future__ import annotations

import csv
from pathlib import Path

from coverage_stats.reporters.models import CoverageReport


class TsvReporter:
    """TSV reporter for coverage stats."""
    def write(self, report: CoverageReport, output_dir: Path) -> None:
        write_tsv(report, output_dir)


def write_tsv(report: CoverageReport, output_dir: Path) -> None:
    rows = []
    for fr in sorted(report.files, key=lambda f: f.summary.rel_path):
        for lr in sorted(fr.lines, key=lambda line_report: line_report.lineno):
            if lr.incidental_executions > 0 or lr.deliberate_executions > 0:
                rows.append((fr.summary.rel_path, lr.lineno, lr.incidental_executions,
                             lr.deliberate_executions, lr.incidental_asserts,
                             lr.deliberate_asserts, lr.incidental_tests, lr.deliberate_tests))

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "coverage-stats.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["file", "lineno", "incidental_executions", "deliberate_executions",
                         "incidental_asserts", "deliberate_asserts", "incidental_tests", "deliberate_tests"])
        for row in rows:
            writer.writerow(list(row))
