from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

import pytest

from coverage_stats.executable_lines import get_executable_lines
from coverage_stats.store import LineData, SessionStore


class _LineStats(TypedDict):
    incidental_executions: int
    deliberate_executions: int
    incidental_asserts: int
    deliberate_asserts: int


class _FileSummary(TypedDict):
    total_stmts: int
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

    # Build abs_path map for executable-line analysis
    abs_path_map: dict[str, str] = {}
    for (abs_path, _lineno) in store._data.keys():
        try:
            rel = Path(abs_path).relative_to(config.rootpath).as_posix()
        except ValueError:
            rel = Path(abs_path).as_posix()
        abs_path_map[rel] = abs_path

    result: _JsonResult = {"files": {}}
    for rel_path, lines in files.items():
        abs_path = abs_path_map.get(rel_path, rel_path)
        executable = get_executable_lines(abs_path)
        total_stmts = len(executable) if executable else len(lines)
        incidental_covered = sum(1 for ld in lines.values() if ld.incidental_executions > 0)
        deliberate_covered = sum(1 for ld in lines.values() if ld.deliberate_executions > 0)
        total_incidental_asserts = sum(ld.incidental_asserts for ld in lines.values())
        total_deliberate_asserts = sum(ld.deliberate_asserts for ld in lines.values())

        incidental_coverage_pct = incidental_covered / total_stmts * 100.0 if total_stmts else 0.0
        deliberate_coverage_pct = deliberate_covered / total_stmts * 100.0 if total_stmts else 0.0
        incidental_assert_density = total_incidental_asserts / total_stmts if total_stmts else 0.0
        deliberate_assert_density = total_deliberate_asserts / total_stmts if total_stmts else 0.0

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
                "total_stmts": total_stmts,
                "incidental_coverage_pct": incidental_coverage_pct,
                "deliberate_coverage_pct": deliberate_coverage_pct,
                "incidental_assert_density": incidental_assert_density,
                "deliberate_assert_density": deliberate_assert_density,
            },
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "coverage-stats.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
