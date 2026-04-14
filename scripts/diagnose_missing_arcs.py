#!/usr/bin/env python3
# mypy: ignore-errors
"""Identify exactly which static arcs coverage-stats misses vs coverage.py.

Runs the test suite, loads both tools' outputs, and computes the set difference
of arcs each tool considers "taken" from the shared static_arcs denominator.
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
    raise FileNotFoundError


def run_tests(pytest_bin, project_dir, source, tests, stats_out, cov_json):
    cmd = [
        str(pytest_bin), tests,
        "--coverage-stats", "--coverage-stats-format=json",
        f"--coverage-stats-output={stats_out}",
        f"--cov={source}", "--cov-branch",
        f"--cov-report=json:{cov_json}",
        "-W", "ignore::coverage.exceptions.CoverageWarning",
        "-p", "no:xdist", "-q",
    ]
    subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True)


def get_static_arcs(source_path: str) -> set[tuple[int, int]] | None:
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
    except Exception:
        return None


def read_source_lines(path: str) -> dict[int, str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return {i + 1: line.rstrip() for i, line in enumerate(f)}
    except OSError:
        return {}


def main():
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    venv_dir = Path(args.venv_dir).resolve()
    pytest_bin = find_pytest(venv_dir)

    with tempfile.TemporaryDirectory(prefix="diag-arcs-") as tmp:
        tmp_path = Path(tmp)
        stats_out = tmp_path / "stats"
        cov_json_path = tmp_path / "coverage.json"

        print("Running tests...", file=sys.stderr)
        run_tests(pytest_bin, project_dir, args.source, args.tests, stats_out, cov_json_path)

        stats_json_path = stats_out / "coverage-stats.json"
        cs_data = json.loads(stats_json_path.read_text())
        cov_data = json.loads(cov_json_path.read_text())

        # We also need the raw store to see our observed arcs.
        # The JSON reporter doesn't include raw arc data.
        # Let's use a different approach: re-derive observed arcs from store.
        # Actually, let's just load the internal store JSON if available.

        # Alternative: use the coverage.py JSON which includes executed_branches
        # and missing_branches, and compute which static arcs *we* observed
        # by looking at our arcs_covered count vs what cov.py says.

        # Better: directly compare. cov.py JSON has executed_branches per file.
        # For our tool, we know arcs_covered. The arcs cov.py observed but we
        # didn't are the ones we need to explain.

        # But we can't see our exact arc set from the JSON report.
        # Let's instead look at the cov.py missing_branches — these are arcs
        # NEITHER tool covers. The arcs cov.py covers but we don't are:
        #   cov_executed_branches ∩ static_arcs - cs_observed_arcs

        # Since we can't get cs_observed_arcs from the JSON report, let's
        # instead look at what coverage.py's executed_branches contain that
        # likely explains the gap, and match to code patterns.

        category_totals: dict[str, list[tuple[str, int, int, str]]] = defaultdict(list)

        for rel_path in sorted(cs_data.get("files", {})):
            cs_summary = cs_data["files"][rel_path]["summary"]

            # Find matching cov.py entry
            cov_file = None
            for cov_key, cov_val in cov_data.get("files", {}).items():
                if cov_key.endswith(rel_path) or rel_path.endswith(cov_key):
                    cov_file = cov_val
                    break
            if cov_file is None:
                continue

            cov_summary = cov_file["summary"]
            cs_arcs_covered = cs_summary.get("arcs_covered", 0)
            cov_br_covered = cov_summary.get("covered_branches", 0)
            if cs_arcs_covered >= cov_br_covered:
                continue

            gap = cov_br_covered - cs_arcs_covered
            abs_path = str(project_dir / rel_path)
            source_lines = read_source_lines(abs_path)
            static_arcs = get_static_arcs(abs_path)
            if static_arcs is None:
                continue

            # cov.py executed branches (as arc pairs)
            cov_executed = {tuple(a) for a in cov_file.get("executed_branches", [])}
            # cov.py missing branches
            cov_missing = {tuple(a) for a in cov_file.get("missing_branches", [])}

            # Arcs that cov.py says are taken AND are in our static_arcs set
            cov_taken_static = cov_executed & static_arcs
            # Arcs that cov.py says are NOT taken AND are in static_arcs
            cov_not_taken_static = cov_missing & static_arcs

            # We know: cs_arcs_covered arcs from static_arcs were taken by us
            # and cov_br_covered = len(cov_taken_static) arcs were taken by cov.py
            # The gap = arcs in cov_taken_static that we didn't observe.
            # We can't identify the EXACT arcs, but we can list the cov_taken_static
            # arcs and flag the ones most likely to be LINE-event-invisible.

            print(f"\n{'='*70}")
            print(f"FILE: {rel_path}")
            print(f"  cs: {cs_arcs_covered}/{len(static_arcs)}, cov: {cov_br_covered}/{len(static_arcs)}, gap: {gap}")
            print(f"  cov_taken_in_static: {len(cov_taken_static)}, cov_not_taken_in_static: {len(cov_not_taken_static)}")

            # Group by source line
            by_source: dict[int, list[tuple[int, bool]]] = defaultdict(list)
            for src, tgt in static_arcs:
                taken = (src, tgt) in cov_taken_static
                by_source[src].append((tgt, taken))

            # Find branch points where cov.py fully covers all arcs
            # (these are candidates for arcs we miss)
            fully_covered_by_cov: list[tuple[int, list[tuple[int, bool]]]] = []
            for src in sorted(by_source):
                arcs = by_source[src]
                if all(taken for _, taken in arcs):
                    fully_covered_by_cov.append((src, arcs))

            # Among these, some we also fully cover, some we don't.
            # The gap is spread across these fully-covered-by-cov branch points.
            # Let's look at the code patterns to identify what we might miss.

            # Key insight: we need to figure out which SPECIFIC arcs we miss.
            # For each fully-covered-by-cov branch point, check if any of its
            # arcs look like they'd be invisible to LINE events.

            print("\n  CANDIDATES (branch points fully covered by cov.py, potential cs gaps):")
            for src, arcs in fully_covered_by_cov:
                src_text = source_lines.get(src, "").strip()
                for tgt, _ in sorted(arcs, key=lambda x: x[0]):
                    tgt_text = source_lines.get(tgt, "").strip() if tgt > 0 else f"<exit scope {-tgt}>"

                    # Flag arcs likely invisible to LINE events:
                    suspicious = False
                    reason = ""

                    # 1. Exit-scope arcs: we record (last_line, -co_firstlineno)
                    #    but coverage.py may use a different scope line
                    if tgt < 0:
                        suspicious = True
                        reason = "exit-scope (co_firstlineno may differ from cov.py scope line)"

                    # 2. Arcs involving comprehension/generator lines
                    #    (separate code objects, LINE events in different context)

                    # 3. Arcs from for-loop header back to itself (loop continuation)
                    if src == tgt:
                        suspicious = True
                        reason = "self-loop (for-header back-edge)"

                    # 4. Arc from for-header to post-loop (iterator exhaustion)
                    #    — Python may not fire a LINE for the for-header when
                    #    the iterator is exhausted on 3.12
                    if ("for " in src_text or "async for" in src_text) and tgt > src:
                        # This is the "false branch" — for-loop to post-loop
                        suspicious = True
                        reason = "for-loop exit (iterator exhaustion may skip LINE)"

                    if suspicious:
                        print(f"    * L{src} -> L{tgt}: {reason}")
                        print(f"      src: {src_text[:70]}")
                        if tgt > 0:
                            print(f"      tgt: {tgt_text[:70]}")

                        cat_key = reason.split("(")[0].strip()
                        category_totals[cat_key].append((rel_path, src, tgt, src_text))

        print(f"\n{'='*70}")
        print("PATTERN SUMMARY")
        print("="*70)
        for cat, entries in sorted(category_totals.items(), key=lambda x: -len(x[1])):
            print(f"\n  {cat}: {len(entries)} arcs")
            for path, src, tgt, text in entries[:5]:
                print(f"    {path}:{src} -> {tgt}: {text[:60]}")
            if len(entries) > 5:
                print(f"    ... and {len(entries) - 5} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
