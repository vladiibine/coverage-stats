#!/usr/bin/env python3
r"""Compare coverage.py and coverage-stats on a project.

Usage:
    python scripts/compare_cov_cs.py <project_dir> <venv_dir> [options]

Arguments:
    project_dir   Root of the project to measure (must contain a pytest-runnable
                  test suite and a pyproject.toml / setup.cfg / pytest.ini that
                  sets ``coverage_stats_source``).
    venv_dir      Path to a virtual environment that has pytest, pytest-cov,
                  coverage, and coverage-stats installed.

Options:
    --source DIR  Source directory passed to --cov (default: src).
    --tests DIR   Test directory passed to pytest (default: tests).
    --output FILE Path for the generated .md report
                  (default: <project_dir>/coverage-comparison.md).
    --precision N Decimal places in reported percentages (default: 4).

The script:
  1. Runs pytest with --coverage-stats (JSON) and --cov (JSON + branch) in one
     pass so both tools see exactly the same test run.
  2. Parses both JSON outputs.
  3. Writes a Markdown report that explains the formulas each tool uses and
     shows a per-file table of raw numbers and computed percentages.

Examples — httpx (coverage-stats-extensive-examples/httpx):

  The httpx example project ships two virtual environments: .venv (Python 3.9)
  and .venv-3.12 (Python 3.12).  Run from the coverage-stats repo root:

  # Python 3.9 venv — full test suite
  python scripts/compare_cov_cs.py coverage-stats-extensive-examples/httpx \
    coverage-stats-extensive-examples/httpx/.venv \
    --source httpx \
    --tests tests \
    --output scripts/output/coverage-comparison-py39.md

  # Python 3.12 venv — full test suite
  python scripts/compare_cov_cs.py \
      coverage-stats-extensive-examples/httpx \
      coverage-stats-extensive-examples/httpx/.venv-3.12 \
      --source httpx --tests tests \
      --output scripts/output/coverage-comparison-py312.md

  To run a single test file instead of the full suite (faster), replace
  ``--tests tests`` with e.g. ``--tests tests/test_auth.py``.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compare coverage.py and coverage-stats on a project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("project_dir", help="Root of the project to measure")
    p.add_argument("venv_dir", help="Virtual environment with all required packages")
    p.add_argument("--source", default="src", help="Source dir for --cov (default: src)")
    p.add_argument("--tests", default="tests", help="Test directory (default: tests)")
    p.add_argument(
        "--output",
        default=None,
        help="Output .md path (default: <project_dir>/coverage-comparison.md)",
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


def run_tests(
    pytest_bin: Path,
    project_dir: Path,
    source: str,
    tests: str,
    stats_out: Path,
    cov_json: Path,
) -> subprocess.CompletedProcess[str]:
    """Run pytest once, collecting data for both tools simultaneously."""
    cmd = [
        str(pytest_bin),
        tests,
        # coverage-stats
        "--coverage-stats",
        "--coverage-stats-format=json",
        f"--coverage-stats-output={stats_out}",
        # coverage.py
        f"--cov={source}",
        "--cov-branch",
        f"--cov-report=json:{cov_json}",
        # Suppress the "CoverageWarning: --include is ignored because --source
        # is set" warning that coverage.py emits when the project config has
        # an `include` key and we also pass --cov=SOURCE.  Projects with
        # filterwarnings=error (e.g. httpx) would otherwise treat this as a
        # test failure.
        "-W", "ignore::coverage.exceptions.CoverageWarning",
        # no xdist — both tracers must see every test
        "-p", "no:xdist",
    ]
    print("Running:", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=project_dir,
        capture_output=False,
        text=True,
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def load_stats_json(stats_json: Path) -> dict[str, dict[str, object]]:
    """Return {rel_path: summary_dict} from coverage-stats JSON."""
    data = json.loads(stats_json.read_text(encoding="utf-8"))
    return {k: v["summary"] for k, v in data.get("files", {}).items()}


def load_cov_json(cov_json: Path) -> dict[str, dict[str, object]]:
    """Return {rel_path: summary_dict} from coverage.py JSON."""
    data = json.loads(cov_json.read_text(encoding="utf-8"))
    return {k: v["summary"] for k, v in data.get("files", {}).items()}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

FORMULA_SECTION = """\
## Formulas

### coverage-stats

```
coverage % = (covered_stmts + covered_arcs) / (total_stmts + total_arcs) × 100
```

- **total_stmts** — executable statements as identified by coverage.py's
  `PythonParser` (when available) or coverage-stats' own AST analyser.
- **covered_stmts** — executable statements executed at least once.
- **total_arcs** — branch arcs whose source line has ≥ 2 reachable targets
  (exit-scope arcs count). Derived from `coverage.PythonParser.arcs()` when
  coverage.py is installed.
- **covered_arcs** — branch arcs that were actually taken.

### coverage.py (with `--cov-branch`)

```
coverage % = (covered_lines + covered_branches) / (num_statements + num_branches) × 100
```

- **num_statements** — executable statements (bytecode-derived).
- **covered_lines** — statements executed at least once.
- **num_branches** — branch arcs (same denominator as coverage-stats when
  coverage-stats is using `PythonParser` arc data).
- **covered_branches** — branch arcs taken.

When coverage-stats has access to coverage.py's `PythonParser`, both tools
share the same denominator (`total_arcs == num_branches`, `total_stmts ==
num_statements`).  Remaining differences are therefore limited to the
**numerator** — specifically, which arcs are counted as "taken".

"""


def _pct(num: float, den: float, precision: int) -> str:
    if den == 0:
        return "100.00"
    return f"{num / den * 100:.{precision}f}"


def _differs_marker(cs_pct: float | None, cov_pct: float | None, precision: int) -> str:
    if cs_pct is None or cov_pct is None:
        return "N/A"
    fmt = f"{{:.{precision}f}}"
    return "**YES**" if fmt.format(cs_pct) != fmt.format(cov_pct) else "no"


def build_report(
    stats: dict[str, dict[str, object]],
    cov: dict[str, dict[str, object]],
    precision: int,
) -> str:
    lines: list[str] = []
    lines.append("# Coverage Comparison: coverage-stats vs coverage.py\n")
    lines.append(FORMULA_SECTION)
    lines.append("## Per-file breakdown\n")

    # Header
    lines.append(
        "| File "
        "| cs stmts "
        "| cov stmts "
        "| cs covered "
        "| cov covered "
        "| cs arcs "
        "| cov branches "
        "| cs arcs covered "
        "| cov br covered "
        "| cs % "
        "| cov % "
        "| differs |"
    )
    lines.append(
        "|-----"
        "|----------:|-----------:|--------:|----------------:|-----:"
        "|----------:|------------:|-------------:|---------------:|-----:"
        "|---------|"
    )

    all_keys = sorted(set(stats) | set(cov))
    differ_count = 0

    for key in all_keys:
        s = stats.get(key)
        c = cov.get(key)

        if s is not None:
            cs_stmts     = s.get("total_stmts", 0)
            cs_covered   = s.get("total_covered", "?")
            cs_arcs      = s.get("arcs_total", 0)
            cs_arcs_cov  = s.get("arcs_covered", 0)
            _cs_pct      = s.get("total_coverage_pct")
            cs_pct_val: float | None = float(_cs_pct) if isinstance(_cs_pct, (int, float)) else None
            cs_pct_str   = f"{cs_pct_val:.{precision}f}" if cs_pct_val is not None else "?"
        else:
            cs_stmts = cs_covered = cs_arcs = cs_arcs_cov = "—"
            cs_pct_str = "—"
            cs_pct_val = None

        if c is not None:
            cov_stmts    = c.get("num_statements", 0)
            cov_covered  = c.get("covered_lines", "?")
            cov_branches = c.get("num_branches", 0)
            cov_br_cov   = c.get("covered_branches", 0)
            _cov_pct     = c.get("percent_covered")
            cov_pct_val: float | None = float(_cov_pct) if isinstance(_cov_pct, (int, float)) else None
            cov_pct_str  = f"{cov_pct_val:.{precision}f}" if cov_pct_val is not None else "?"
        else:
            cov_stmts = cov_covered = cov_branches = cov_br_cov = "—"
            cov_pct_str = "—"
            cov_pct_val = None

        marker = _differs_marker(cs_pct_val, cov_pct_val, precision)
        if marker == "**YES**":
            differ_count += 1

        # Truncate long paths from the left for readability
        display = key if len(key) <= 60 else "…" + key[-59:]

        lines.append(
            f"| `{display}` "
            f"| {cs_stmts} "
            f"| {cov_stmts} "
            f"| {cs_covered} "
            f"| {cov_covered} "
            f"| {cs_arcs} "
            f"| {cov_branches} "
            f"| {cs_arcs_cov} "
            f"| {cov_br_cov} "
            f"| {cs_pct_str} "
            f"| {cov_pct_str}"
            f" | {marker} |"
        )

    lines.append("")
    total = len(all_keys)
    lines.append(
        f"**{differ_count} of {total} files differ** at {precision} decimal places.\n"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()

    project_dir = Path(args.project_dir).resolve()
    venv_dir    = Path(args.venv_dir).resolve()
    output_path = Path(args.output).resolve() if args.output else project_dir / "coverage-comparison.md"

    if not project_dir.is_dir():
        print(f"error: project_dir not found: {project_dir}", file=sys.stderr)
        return 1
    if not venv_dir.is_dir():
        print(f"error: venv_dir not found: {venv_dir}", file=sys.stderr)
        return 1

    pytest_bin = find_pytest(venv_dir)

    with tempfile.TemporaryDirectory(prefix="cov-compare-") as tmp:
        tmp_path  = Path(tmp)
        stats_out = tmp_path / "stats"
        cov_json  = tmp_path / "coverage.json"

        result = run_tests(
            pytest_bin,
            project_dir,
            args.source,
            args.tests,
            stats_out,
            cov_json,
        )

        stats_json = stats_out / "coverage-stats.json"
        if not stats_json.exists():
            print(f"error: coverage-stats JSON not produced at {stats_json}", file=sys.stderr)
            print("pytest exit code:", result.returncode, file=sys.stderr)
            return 1
        if not cov_json.exists():
            print(f"error: coverage.py JSON not produced at {cov_json}", file=sys.stderr)
            print("pytest exit code:", result.returncode, file=sys.stderr)
            return 1

        stats = load_stats_json(stats_json)
        cov   = load_cov_json(cov_json)

    report = build_report(stats, cov, args.precision)
    output_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
