#!/usr/bin/env python3
# mypy: ignore-errors
"""Identify EXACTLY which static arcs coverage-stats misses.

Runs tests, collects the raw SessionStore arc data, and compares
against coverage.py's executed_branches to find the exact set difference.
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

    with tempfile.TemporaryDirectory(prefix="exact-arcs-") as tmp:
        tmp_path = Path(tmp)
        stats_out = tmp_path / "stats"
        cov_json_path = tmp_path / "coverage.json"
        # Also dump the raw store
        store_dump = tmp_path / "raw_store.json"

        # Write a conftest that dumps the raw store at session end
        conftest_path = project_dir / "conftest_dump_store.py"
        conftest_path.write_text(f'''
import json, atexit
def pytest_sessionfinish(session, exitstatus):
    for plugin in session.config.pluginmanager.get_plugins():
        store = getattr(plugin, "_store", None)
        if store is not None and hasattr(store, "to_dict"):
            with open("{store_dump}", "w") as f:
                json.dump(store.to_dict(), f)
            break
''')

        cmd = [
            str(pytest_bin), args.tests,
            "--coverage-stats", "--coverage-stats-format=json",
            f"--coverage-stats-output={stats_out}",
            f"--cov={args.source}", "--cov-branch",
            f"--cov-report=json:{cov_json_path}",
            "-W", "ignore::coverage.exceptions.CoverageWarning",
            "-p", "no:xdist", "-q",
        ]
        print("Running tests...", file=sys.stderr)
        subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True)
        conftest_path.unlink(missing_ok=True)

        cov_data = json.loads(cov_json_path.read_text())
        cs_data = json.loads((stats_out / "coverage-stats.json").read_text())

        # Load raw store if available
        if store_dump.exists():
            store_raw = json.loads(store_dump.read_text())
        else:
            print("WARNING: raw store dump not available, falling back to approximation")
            store_raw = None

        # Extract observed arcs from raw store
        cs_observed_arcs: dict[str, set[tuple[int, int]]] = defaultdict(set)
        if store_raw:
            arc_section = store_raw.get("arcs", {})
            for raw_key, values in arc_section.items():
                parts = raw_key.split("\x00")
                path = parts[0]
                from_line = int(parts[1])
                to_line = int(parts[2])
                inc, delib = values[0], values[1]
                if inc > 0 or delib > 0:
                    cs_observed_arcs[path].add((from_line, to_line))

        category_counts: dict[str, int] = defaultdict(int)
        total_gap = 0

        for rel_path in sorted(cs_data.get("files", {})):
            cs_summary = cs_data["files"][rel_path]["summary"]
            # Find cov.py entry
            cov_file = None
            for ck, cv in cov_data.get("files", {}).items():
                if ck.endswith(rel_path) or rel_path.endswith(ck):
                    cov_file = cv
                    break
            if cov_file is None:
                continue

            cov_summary = cov_file["summary"]
            cs_arc_cov = cs_summary.get("arcs_covered", 0)
            cov_br_cov = cov_summary.get("covered_branches", 0)
            if cs_arc_cov >= cov_br_cov:
                continue

            abs_path = str(project_dir / rel_path)
            source_lines = read_source_lines(abs_path)
            static_arcs = get_static_arcs(abs_path)
            if static_arcs is None:
                continue

            cov_executed = {tuple(a) for a in cov_file.get("executed_branches", [])}
            cov_taken_static = cov_executed & static_arcs

            # Our observed arcs for this file
            cs_arcs = cs_observed_arcs.get(abs_path, set())
            # Which static arcs did we observe?
            cs_taken_static = cs_arcs & static_arcs

            # The EXACT arcs cov.py saw but we didn't:
            missing = cov_taken_static - cs_taken_static
            gap = len(missing)
            total_gap += gap

            if not missing:
                # Gap might be due to different abs_path resolution
                print(f"\n{rel_path}: gap={cov_br_cov - cs_arc_cov} but couldn't find exact missing arcs")
                print(f"  cs observed arcs for file: {len(cs_arcs)}, cs_taken_static: {len(cs_taken_static)}, cov_taken_static: {len(cov_taken_static)}")
                # Try normalized path
                for p in cs_observed_arcs:
                    if rel_path in p:
                        alt_arcs = cs_observed_arcs[p]
                        alt_taken = alt_arcs & static_arcs
                        alt_missing = cov_taken_static - alt_taken
                        if alt_missing != missing:
                            print(f"  Found via alt path {p}: {len(alt_taken)} taken, {len(alt_missing)} missing")
                            missing = alt_missing
                            gap = len(missing)
                continue

            print(f"\n{'='*70}")
            print(f"{rel_path}: {gap} missing arcs (cs: {cs_arc_cov}, cov: {cov_br_cov})")

            for src, tgt in sorted(missing):
                src_text = source_lines.get(src, "???").strip()
                tgt_text = source_lines.get(tgt, "???").strip() if tgt > 0 else f"<exit scope {-tgt}>"

                # Categorize
                if tgt < 0:
                    cat = "exit-scope"
                elif "for " in src_text or "async for " in src_text:
                    cat = "for-loop-arc"
                elif src_text.startswith("if ") or src_text.startswith("elif "):
                    cat = "if-branch"
                elif "if " in src_text:
                    cat = "if-branch-inline"
                else:
                    cat = "other"

                category_counts[cat] += 1
                print(f"  ({src}, {tgt:>5}) [{cat}]")
                print(f"    src L{src}: {src_text[:75]}")
                if tgt > 0:
                    print(f"    tgt L{tgt}: {tgt_text[:75]}")

                # Check what our tracer DID record from this source line
                cs_from_src = {(s, t) for s, t in cs_arcs if s == src}
                if cs_from_src:
                    print(f"    cs saw from L{src}: {sorted(cs_from_src)}")
                else:
                    print(f"    cs saw NOTHING from L{src}")

        print(f"\n{'='*70}")
        print(f"TOTAL: {total_gap} missing arcs across all files")
        print("\nBy category:")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
