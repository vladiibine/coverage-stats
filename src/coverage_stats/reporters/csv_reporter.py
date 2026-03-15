from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
import pytest

from coverage_stats.store import LineData, SessionStore


def write_csv(store: SessionStore, config: pytest.Config, output_dir: Path) -> None:
    files: dict[str, dict[int, LineData]] = defaultdict(dict)
    for (abs_path, lineno), ld in store._data.items():
        try:
            rel = Path(abs_path).relative_to(config.rootpath).as_posix()
        except ValueError:
            rel = Path(abs_path).as_posix()
        files[rel][lineno] = ld

    rows = []
    for rel_path, lines in files.items():
        for lineno, ld in lines.items():
            rows.append((rel_path, lineno, ld))

    rows.sort(key=lambda r: (r[0], r[1]))

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "coverage-stats.csv"
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["file", "lineno", "incidental_executions", "deliberate_executions", "incidental_asserts", "deliberate_asserts"]
        )
        for rel_path, lineno, ld in rows:
            writer.writerow(
                [rel_path, lineno, ld.incidental_executions, ld.deliberate_executions, ld.incidental_asserts, ld.deliberate_asserts]
            )
