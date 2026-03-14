"""
CLI entry point: coverage-stats html

Usage:
    coverage-stats html
    coverage-stats html --data-file .coverage --meta-file .coverage-stats-meta.json --output htmlcov_stats
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_html(args: argparse.Namespace) -> int:
    data_file = Path(args.data_file)
    meta_file = Path(args.meta_file)
    output_dir = Path(args.output)

    if not data_file.exists():
        print(f"error: coverage data file not found: {data_file}", file=sys.stderr)
        print("       Run your tests with coverage first, e.g.:", file=sys.stderr)
        print("         pytest --cov=src", file=sys.stderr)
        return 1

    if not meta_file.exists():
        print(
            f"warning: coverage-stats metadata not found: {meta_file}\n"
            "         All hits will be counted as incidental.\n"
            "         Make sure the coverage-stats pytest plugin is active.",
            file=sys.stderr,
        )

    print(f"Loading coverage data from {data_file} ...")
    from coverage_stats.analyzer import analyze

    try:
        file_stats = analyze(
            coverage_data_path=data_file,
            meta_path=meta_file,
        )
    except Exception as exc:
        print(f"error: failed to analyze coverage data: {exc}", file=sys.stderr)
        return 1

    if not file_stats:
        print("No measured files found in coverage data.")
        return 0

    print(f"Generating HTML report for {len(file_stats)} file(s) ...")
    from coverage_stats.reporter import generate_html

    out_path = generate_html(file_stats, output_dir=output_dir)
    print(f"Report written to {out_path}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="coverage-stats",
        description="Enhanced coverage reporting: direct vs incidental line hits",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    html_parser = subparsers.add_parser(
        "html",
        help="Generate enhanced HTML report",
    )
    html_parser.add_argument(
        "--data-file",
        default=".coverage",
        metavar="PATH",
        help="Path to the .coverage data file (default: .coverage)",
    )
    html_parser.add_argument(
        "--meta-file",
        default=".coverage-stats-meta.json",
        metavar="PATH",
        help="Path to the coverage-stats metadata file (default: .coverage-stats-meta.json)",
    )
    html_parser.add_argument(
        "--output",
        default="htmlcov_stats",
        metavar="DIR",
        help="Output directory for the HTML report (default: htmlcov_stats)",
    )

    args = parser.parse_args(argv)

    if args.command == "html":
        sys.exit(cmd_html(args))
