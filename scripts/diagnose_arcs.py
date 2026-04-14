#!/usr/bin/env python3
# mypy: ignore-errors
"""Diagnose which static arcs coverage-stats misses vs coverage.py.

Run from the coverage-stats repo root after installing into the httpx venv:

    python scripts/diagnose_arcs.py \
        coverage-stats-extensive-examples/httpx \
        coverage-stats-extensive-examples/httpx/.venv-3.12 \
        --source httpx --tests tests

Produces a per-file breakdown of which static arcs were observed by cs and
which were not, with source-line context.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from collections import defaultdict


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("project_dir")
    p.add_argument("venv_dir")
    p.add_argument("--source", default="src")
    p.add_argument("--tests", default="tests")
    return p.parse_args()


def find_pytest(venv_dir: Path) -> Path:
    for c in (venv_dir / "bin" / "pytest", venv_dir / "Scripts" / "pytest.exe"):
        if c.exists():
            return c
    raise FileNotFoundError(f"pytest not found in {venv_dir}")


def run_tests(pytest_bin, project_dir, source, tests, stats_out, cov_json):
    cmd = [
        str(pytest_bin), tests,
        "--coverage-stats", "--coverage-stats-format=json",
        f"--coverage-stats-output={stats_out}",
        f"--cov={source}", "--cov-branch",
        f"--cov-report=json:{cov_json}",
        "-W", "ignore::coverage.exceptions.CoverageWarning",
        "-p", "no:xdist",
        "-q",
    ]
    subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True)


def get_static_arcs(source_path: str) -> set[tuple[int, int]] | None:
    """Get static arcs for a file using coverage.py's PythonParser."""
    try:
        from coverage.python import PythonParser
        from coverage.config import CoverageConfig
        cfg = CoverageConfig()
        exclude_re = "(" + ")|(".join(cfg.exclude_list) + ")"
    except ImportError:
        return None

    try:
        with open(source_path, encoding="utf-8", errors="replace") as f:
            source = f.read()
        p = PythonParser(text=source, exclude=exclude_re)
        p.parse_source()
        excl = set(p.excluded)

        arc_map: dict[int, set[int]] = defaultdict(set)
        for a, b in p.arcs():
            if a > 0:
                arc_map[a].add(b)

        static_arcs: set[tuple[int, int]] = set()
        for src_ln, targets in arc_map.items():
            if src_ln in excl:
                continue
            countable = [t for t in targets if t < 0 or (t > 0 and t not in excl)]
            if len(countable) >= 2:
                for t in countable:
                    static_arcs.add((src_ln, t))
        return static_arcs
    except Exception as e:
        print(f"  Error getting static arcs: {e}")
        return None


def get_observed_arcs_from_store(store_json: dict, abs_path: str) -> dict[tuple[int, int], tuple[int, int]]:
    """Extract observed arcs for a file from the coverage-stats JSON store.

    Returns {(from_line, to_line): (incidental_exec, deliberate_exec)}
    """
    arcs = {}
    arc_data = store_json.get("arcs", {})
    for raw_key, values in arc_data.items():
        parts = raw_key.split("\x00")
        path = parts[0]
        if path != abs_path:
            continue
        from_line = int(parts[1])
        to_line = int(parts[2])
        inc, delib = values[0], values[1]
        if inc > 0 or delib > 0:
            arcs[(from_line, to_line)] = (inc, delib)
    return arcs


def read_source_lines(path: str) -> dict[int, str]:
    """Read source file and return {lineno: text}."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return {i + 1: line.rstrip() for i, line in enumerate(f)}
    except OSError:
        return {}


def categorize_arc(src: int, tgt: int, source_lines: dict[int, str]) -> str:
    """Try to categorize what kind of arc this is."""
    src_text = source_lines.get(src, "").strip()

    if tgt < 0:
        return "exit-scope"

    # Check for common patterns
    if src_text.startswith("if ") or src_text.startswith("elif "):
        return "if-branch"
    if src_text.startswith("for ") or src_text.startswith("async for "):
        return "for-loop"
    if src_text.startswith("while "):
        return "while-loop"
    if "if " in src_text and src_text.endswith(":"):
        return "if-branch"

    # Could be return from comprehension, try/except, etc.
    return "other"


def main():
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    venv_dir = Path(args.venv_dir).resolve()
    pytest_bin = find_pytest(venv_dir)

    with tempfile.TemporaryDirectory(prefix="diag-arcs-") as tmp:
        tmp_path = Path(tmp)
        stats_out = tmp_path / "stats"
        cov_json_path = tmp_path / "coverage.json"

        print("Running tests...")
        run_tests(pytest_bin, project_dir, args.source, args.tests, stats_out, cov_json_path)

        stats_json_path = stats_out / "coverage-stats.json"
        if not stats_json_path.exists():
            print("ERROR: coverage-stats JSON not found")
            return 1

        stats_data = json.loads(stats_json_path.read_text())
        cov_data = json.loads(cov_json_path.read_text())

        # We need the raw store data, but the JSON reporter writes the report,
        # not the raw store.  Instead, let's compute observed arcs from the
        # coverage-stats JSON report's line data + compare with cov.py's arcs.

        # Actually, let's use the coverage.py JSON to get which arcs were observed
        # by coverage.py, and compare with what cs reports.

        print("\n" + "=" * 80)
        print("ARC DIAGNOSIS: arcs coverage.py observed but coverage-stats missed")
        print("=" * 80)

        category_counts: dict[str, int] = defaultdict(int)

        for rel_path in sorted(stats_data.get("files", {})):
            cs_file = stats_data["files"][rel_path]
            cs_summary = cs_file["summary"]

            # Find matching cov.py entry
            cov_file_data = None
            for cov_key, cov_val in cov_data.get("files", {}).items():
                if cov_key.endswith(rel_path) or rel_path.endswith(cov_key):
                    cov_file_data = cov_val
                    break

            if cov_file_data is None:
                continue

            cov_summary = cov_file_data["summary"]
            cs_arcs_covered = cs_summary.get("arcs_covered", 0)
            cov_br_covered = cov_summary.get("covered_branches", 0)

            if cs_arcs_covered == cov_br_covered:
                continue

            gap = cov_br_covered - cs_arcs_covered

            # Get the absolute path for this file
            abs_path = cs_summary.get("abs_path", "")
            if not abs_path:
                # Construct from project_dir
                abs_path = str(project_dir / rel_path)

            source_lines = read_source_lines(abs_path)
            static_arcs = get_static_arcs(abs_path)

            if static_arcs is None:
                print(f"\n### {rel_path}: gap={gap} (could not get static arcs)")
                continue

            # Get coverage.py's executed arcs for this file
            cov_executed_arcs = set()
            for arc_pair in cov_file_data.get("executed_branches", []):
                cov_executed_arcs.add(tuple(arc_pair))

            # Get coverage.py's missing arcs for this file
            cov_missing_arcs = set()
            for arc_pair in cov_file_data.get("missing_branches", []):
                cov_missing_arcs.add(tuple(arc_pair))

            # Now we need to figure out which of those our tracer also saw.
            # We don't have the raw store here, but we can infer from the gap.
            # cs says cs_arcs_covered taken, cov says cov_br_covered taken.
            # The arcs cov.py took but cs didn't = the gap.

            print(f"\n### {rel_path}")
            print(f"    cs: {cs_arcs_covered}/{len(static_arcs)} arcs, cov: {cov_br_covered}/{len(static_arcs)} arcs, gap: {gap}")

            # List arcs that cov.py marks as executed AND are branch arcs
            # We can't directly see our observed arcs from the JSON report.
            # But we CAN look at coverage.py's executed_branches and missing_branches
            # to understand the full picture.

            # Actually, let's approach differently: show the source context for
            # every branch point (source line in static_arcs) and whether cov.py
            # says each arc was taken
            branch_points: dict[int, list[tuple[int, bool]]] = defaultdict(list)
            for src, tgt in static_arcs:
                taken_by_cov = (src, tgt) in cov_executed_arcs
                branch_points[src].append((tgt, taken_by_cov))

            # Show only branch points where ALL arcs are taken by cov.py
            # (these are the ones where cs likely misses some)
            for src_line in sorted(branch_points):
                arcs = branch_points[src_line]
                all_taken = all(taken for _, taken in arcs)

                if not all_taken:
                    continue  # Not fully covered by cov.py either — not our problem

                src_text = source_lines.get(src_line, "???").strip()
                targets_str = ", ".join(
                    f"{tgt}{'*' if tgt < 0 else ''}"
                    for tgt, _ in sorted(arcs, key=lambda x: x[0])
                )
                cat = categorize_arc(src_line, arcs[0][0], source_lines)
                category_counts[cat] += len(arcs)

                # Only show if this is likely one cs misses (all taken by cov)
                print(f"    Line {src_line}: {src_text[:80]}")
                print(f"      targets: [{targets_str}]  category: {cat}")

        print("\n" + "=" * 80)
        print("Category summary (all arcs from fully-covered-by-cov branch points):")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count} arcs")

    return 0


if __name__ == "__main__":
    sys.exit(main())
