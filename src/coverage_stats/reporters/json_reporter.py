from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def write_json(store, config, output_dir: Path) -> None:
    files: dict[str, dict] = defaultdict(dict)
    for (abs_path, lineno), ld in store._data.items():
        try:
            rel = Path(abs_path).relative_to(Path(str(config.rootdir))).as_posix()
        except ValueError:
            rel = Path(abs_path).as_posix()
        files[rel][lineno] = ld

    result: dict = {"files": {}}
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

        lines_dict = {
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
