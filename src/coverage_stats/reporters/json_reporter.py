from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

import pytest

from coverage_stats.store import LineData, SessionStore


class _LineStats(TypedDict):
    incidental_executions: int
    deliberate_executions: int
    incidental_asserts: int
    deliberate_asserts: int


class _FileSummary(TypedDict):
    total_lines: int
    incidental_coverage_pct: float
    deliberate_coverage_pct: float
    incidental_assert_density: float
    deliberate_assert_density: float


class _FileData(TypedDict):
    lines: dict[str, _LineStats]
    summary: _FileSummary


class _JsonResult(TypedDict):
    files: dict[str, _FileData]


def write_json(store: SessionStore, config: pytest.Config, output_dir: Path) -> None:
    files: dict[str, dict[int, LineData]] = defaultdict(dict)
    for (abs_path, lineno), ld in store._data.items():
        try:
            rel = Path(abs_path).relative_to(config.rootpath).as_posix()
        except ValueError:
            rel = Path(abs_path).as_posix()
        files[rel][lineno] = ld

    result: _JsonResult = {"files": {}}
    for rel_path, lines in files.items():
        total_lines = len(lines)
        incidental_covered = sum(1 for ld in lines.values() if ld.incidental_executions > 0)
        deliberate_covered = sum(1 for ld in lines.values() if ld.deliberate_executions > 0)
        total_incidental_asserts = sum(ld.incidental_asserts for ld in lines.values())
        total_deliberate_asserts = sum(ld.deliberate_asserts for ld in lines.values())

        incidental_coverage_pct = incidental_covered / total_lines * 100.0 if total_lines else 0.0
        deliberate_coverage_pct = deliberate_covered / total_lines * 100.0 if total_lines else 0.0
        incidental_assert_density = total_incidental_asserts / total_lines if total_lines else 0.0
        deliberate_assert_density = total_deliberate_asserts / total_lines if total_lines else 0.0

        lines_dict: dict[str, _LineStats] = {
            str(lineno): {
                "incidental_executions": ld.incidental_executions,
                "deliberate_executions": ld.deliberate_executions,
                "incidental_asserts": ld.incidental_asserts,
                "deliberate_asserts": ld.deliberate_asserts,
            }
            for lineno, ld in lines.items()
        }

        result["files"][rel_path] = {
            "lines": lines_dict,
            "summary": {
                "total_lines": total_lines,
                "incidental_coverage_pct": incidental_coverage_pct,
                "deliberate_coverage_pct": deliberate_coverage_pct,
                "incidental_assert_density": incidental_assert_density,
                "deliberate_assert_density": deliberate_assert_density,
            },
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "coverage-stats.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
