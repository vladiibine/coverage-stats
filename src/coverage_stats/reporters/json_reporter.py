from __future__ import annotations

import json
from pathlib import Path

from coverage_stats.reporters.report_data import CoverageReport


class JsonReporter:
    def write(self, report: CoverageReport, output_dir: Path) -> None:
        write_json(report, output_dir)


def write_json(report: CoverageReport, output_dir: Path) -> None:
    result: dict[str, object] = {"files": {}}
    for fr in report.files:
        total_stmts = fr.summary.total_stmts
        total_inc_asserts = sum(lr.incidental_asserts for lr in fr.lines)
        total_del_asserts = sum(lr.deliberate_asserts for lr in fr.lines)
        inc_density = total_inc_asserts / total_stmts if total_stmts else 0.0
        del_density = total_del_asserts / total_stmts if total_stmts else 0.0

        lines_dict = {
            str(lr.lineno): {
                "incidental_executions": lr.incidental_executions,
                "deliberate_executions": lr.deliberate_executions,
                "incidental_asserts": lr.incidental_asserts,
                "deliberate_asserts": lr.deliberate_asserts,
                "incidental_tests": lr.incidental_tests,
                "deliberate_tests": lr.deliberate_tests,
            }
            for lr in fr.lines
            if lr.incidental_executions > 0 or lr.deliberate_executions > 0
        }

        result["files"][fr.summary.rel_path] = {  # type: ignore[index]
            "lines": lines_dict,
            "summary": {
                "total_stmts": total_stmts,
                "total_coverage_pct": fr.summary.total_pct,
                "incidental_coverage_pct": fr.summary.incidental_pct,
                "deliberate_coverage_pct": fr.summary.deliberate_pct,
                "incidental_assert_density": inc_density,
                "deliberate_assert_density": del_density,
            },
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "coverage-stats.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
