#!/usr/bin/env python3
r"""Compare coverage.py output when run standalone vs together with coverage-stats.

Runs the test suite twice: once without coverage-stats (baseline) and once
with coverage-stats enabled, then diffs the coverage.py JSON reports.
Differences mean coverage-stats is affecting what coverage.py reports — ideally
the table should be empty.

Usage:
    python scripts/compare_standalone_vs_with_cs.py <project_dir> <venv_dir> [options]

Arguments:
    project_dir   Root of the project to measure.
    venv_dir      Virtual environment with pytest, pytest-cov, coverage, and
                  coverage-stats installed.

Options:
    --source DIR  Source directory passed to --cov (default: src).
    --tests DIR   Test directory / file passed to pytest (default: tests).
    --output FILE Path for the generated .md report
                  (default: <project_dir>/standalone-vs-with-cs.md).
    --precision N Decimal places in reported percentages (default: 4).

Examples — httpx:

  python scripts/compare_standalone_vs_with_cs.py \
      coverage-stats-extensive-examples/httpx \
      coverage-stats-extensive-examples/httpx/.venv \
      --source httpx \
      --tests tests \
      --output scripts/output/standalone-vs-with-cs-py39.md

  python scripts/compare_standalone_vs_with_cs.py \
      coverage-stats-extensive-examples/httpx \
      coverage-stats-extensive-examples/httpx/.venv-3.12 \
      --source httpx \
      --tests tests \
      --output scripts/output/standalone-vs-with-cs-py312.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compare coverage.py standalone vs with coverage-stats.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("project_dir", help="Root of the project to measure")
    p.add_argument("venv_dir", help="Virtual environment with all required packages")
    p.add_argument("--source", default="src", help="Source dir for --cov (default: src)")
    p.add_argument("--tests", default="tests", help="Test directory (default: tests)")
    p.add_argument(
        "--output",
        default=None,
        help="Output .md path (default: <project_dir>/standalone-vs-with-cs.md)",
    )
    p.add_argument("--precision", type=int, default=4, help="Decimal places (default: 4)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Running the tests
# ---------------------------------------------------------------------------

def find_pytest(venv_dir: Path) -> Path:
    for candidate in (
        venv_dir / "bin" / "pytest",
        venv_dir / "Scripts" / "pytest.exe",
        venv_dir / "Scripts" / "pytest",
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"pytest not found inside {venv_dir}")


def _base_cmd(
    pytest_bin: Path,
    tests: str,
    source: str,
    cov_json: Path,
    cov_html: Path,
) -> list[str]:
    return [
        str(pytest_bin),
        tests,
        f"--cov={source}",
        "--cov-branch",
        f"--cov-report=json:{cov_json}",
        f"--cov-report=html:{cov_html}",
        "-W", "ignore::coverage.exceptions.CoverageWarning",
        "-p", "no:xdist",
        "-q", "--tb=no",
    ]


def run_standalone(
    pytest_bin: Path,
    project_dir: Path,
    source: str,
    tests: str,
    cov_json: Path,
    cov_html: Path,
) -> subprocess.CompletedProcess[str]:
    """Run pytest without coverage-stats (baseline)."""
    cmd = _base_cmd(pytest_bin, tests, source, cov_json, cov_html) + ["-p", "no:coverage_stats"]
    print(f"\n[1/2] Standalone run (no coverage-stats):\n  {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=project_dir, capture_output=False, text=True)


def run_with_cs(
    pytest_bin: Path,
    project_dir: Path,
    source: str,
    tests: str,
    cov_json: Path,
    cov_html: Path,
) -> subprocess.CompletedProcess[str]:
    """Run pytest with coverage-stats enabled."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rand = uuid.uuid4().hex[:8]
    cs_output = f"/tmp/delete-this-{rand}-{stamp}"
    cmd = _base_cmd(pytest_bin, tests, source, cov_json, cov_html) + [
        "--coverage-stats",
        "--coverage-stats-format=json",
        f"--coverage-stats-output={cs_output}",
        f"--coverage-stats-source={source}",
    ]
    print(f"\n[2/2] With coverage-stats (cs output: {cs_output}):\n  {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=project_dir, capture_output=False, text=True)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def load_cov_json(path: Path) -> dict[str, dict[str, object]]:
    """Return {abs_path: summary_dict} from a coverage.py JSON report."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v["summary"] for k, v in data.get("files", {}).items()}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt(val: object, precision: int) -> str:
    if isinstance(val, (int, float)):
        return f"{val:.{precision}f}" if isinstance(val, float) else str(val)
    return str(val) if val is not None else "?"


def build_report(
    standalone: dict[str, dict[str, object]],
    with_cs: dict[str, dict[str, object]],
    precision: int,
    html_standalone: Path,
    html_with_cs: Path,
) -> str:
    lines: list[str] = []
    lines.append("# coverage.py: Standalone vs With coverage-stats\n")
    lines.append(
        "Differences in this table mean coverage-stats is affecting what coverage.py reports.\n"
        "An empty differences section means both runs produce identical output — the ideal result.\n"
    )
    lines.append("## HTML reports\n")
    lines.append(f"- [Standalone (no coverage-stats)]({html_standalone / 'index.html'})")
    lines.append(f"- [With coverage-stats]({html_with_cs / 'index.html'})")
    lines.append("")

    # --- collect per-file rows ---
    all_keys = sorted(set(standalone) | set(with_cs))
    differ_rows: list[str] = []
    agree_rows: list[str] = []

    for key in all_keys:
        sa = standalone.get(key, {})
        cs = with_cs.get(key, {})

        sa_lines   = sa.get("covered_lines", 0)
        sa_br      = sa.get("covered_branches", 0)
        sa_stmts   = sa.get("num_statements", 0)
        sa_num_br  = sa.get("num_branches", 0)
        sa_pct     = sa.get("percent_covered")

        cs_lines   = cs.get("covered_lines", 0)
        cs_br      = cs.get("covered_branches", 0)
        cs_stmts   = cs.get("num_statements", 0)
        cs_num_br  = cs.get("num_branches", 0)
        cs_pct     = cs.get("percent_covered")

        differs = (
            sa_lines != cs_lines
            or sa_br != cs_br
            or sa_stmts != cs_stmts
            or sa_num_br != cs_num_br
        )

        delta_lines = (cs_lines if isinstance(cs_lines, int) else 0) - (sa_lines if isinstance(sa_lines, int) else 0)
        delta_br    = (cs_br if isinstance(cs_br, int) else 0) - (sa_br if isinstance(sa_br, int) else 0)

        delta_lines_str = f"{delta_lines:+d}" if delta_lines != 0 else "—"
        delta_br_str    = f"{delta_br:+d}"    if delta_br    != 0 else "—"

        display = key if len(key) <= 55 else "…" + key[-54:]

        sa_pct_str = f"{sa_pct:.{precision}f}" if isinstance(sa_pct, float) else "?"
        cs_pct_str = f"{cs_pct:.{precision}f}" if isinstance(cs_pct, float) else "?"

        row = (
            f"| `{display}` "
            f"| {sa_stmts} | {sa_lines} | {sa_num_br} | {sa_br} | {sa_pct_str} "
            f"| {cs_stmts} | {cs_lines} | {cs_num_br} | {cs_br} | {cs_pct_str} "
            f"| {delta_lines_str} | {delta_br_str} |"
        )
        if differs:
            differ_rows.append(row)
        else:
            agree_rows.append(row)

    header = (
        "| File "
        "| sa stmts | sa cov lines | sa branches | sa cov br | sa % "
        "| cs stmts | cs cov lines | cs branches | cs cov br | cs % "
        "| Δ lines | Δ branches |"
    )
    sep = (
        "|-----"
        "|----------:|-------------:|------------:|----------:|------:"
        "|----------:|-------------:|------------:|----------:|------:"
        "|--------:|--------:|"
    )

    differ_count = len(differ_rows)
    total = len(all_keys)

    lines.append(f"## Files with differences ({differ_count} of {total})\n")
    if differ_rows:
        lines.append(header)
        lines.append(sep)
        lines.extend(differ_rows)
    else:
        lines.append("_No differences — coverage.py reports identical results with and without coverage-stats._")
    lines.append("")

    lines.append(f"## Files that agree ({len(agree_rows)} of {total})\n")
    if agree_rows:
        lines.append(header)
        lines.append(sep)
        lines.extend(agree_rows)
    else:
        lines.append("_All files differ._")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()

    project_dir = Path(args.project_dir).resolve()
    venv_dir    = Path(args.venv_dir).resolve()
    output_path = (
        Path(args.output).resolve()
        if args.output
        else project_dir / "standalone-vs-with-cs.md"
    )

    if not project_dir.is_dir():
        print(f"error: project_dir not found: {project_dir}", file=sys.stderr)
        return 1
    if not venv_dir.is_dir():
        print(f"error: venv_dir not found: {venv_dir}", file=sys.stderr)
        return 1

    pytest_bin = find_pytest(venv_dir)

    # HTML reports live next to the output .md so they persist after the run.
    stem = output_path.stem
    html_standalone = output_path.parent / f"{stem}-standalone-html"
    html_with_cs    = output_path.parent / f"{stem}-with-cs-html"

    with tempfile.TemporaryDirectory(prefix="cov-sa-vs-cs-") as tmp:
        tmp_path       = Path(tmp)
        cov_json_sa    = tmp_path / "cov_standalone.json"
        cov_json_cs    = tmp_path / "cov_with_cs.json"

        run_standalone(pytest_bin, project_dir, args.source, args.tests, cov_json_sa, html_standalone)
        run_with_cs(pytest_bin, project_dir, args.source, args.tests, cov_json_cs, html_with_cs)

        if not cov_json_sa.exists():
            print(f"error: standalone coverage.py JSON not produced at {cov_json_sa}", file=sys.stderr)
            return 1
        if not cov_json_cs.exists():
            print(f"error: with-cs coverage.py JSON not produced at {cov_json_cs}", file=sys.stderr)
            return 1

        standalone = load_cov_json(cov_json_sa)
        with_cs    = load_cov_json(cov_json_cs)

    report = build_report(standalone, with_cs, args.precision, html_standalone, html_with_cs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {output_path}")
    print(f"HTML (standalone):   {html_standalone / 'index.html'}")
    print(f"HTML (with cs):      {html_with_cs / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
