#!/usr/bin/env python3
"""Dump coverage-stats observed arcs for comparison with coverage.py.

Runs the test suite with a small inline plugin that extracts the raw arc
data from the SessionStore after tests finish.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("project_dir")
    p.add_argument("venv_dir")
    p.add_argument("--source", default="src")
    p.add_argument("--tests", default="tests")
    p.add_argument("--output", required=True, help="Path for arc dump JSON")
    return p.parse_args()


def find_pytest(venv_dir: Path) -> Path:
    for c in (venv_dir / "bin" / "pytest", venv_dir / "Scripts" / "pytest.exe"):
        if c.exists():
            return c
    raise FileNotFoundError


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    venv_dir = Path(args.venv_dir).resolve()
    pytest_bin = find_pytest(venv_dir)
    output_path = Path(args.output).resolve()

    # Write a conftest.py plugin file into a temp directory and add it to
    # confcutdir so pytest loads it
    with tempfile.TemporaryDirectory(prefix="arc-dump-") as tmp:
        plugin_file = Path(tmp) / "conftest.py"
        plugin_file.write_text(f'''
import json
import pytest

class _ArcDumper:
    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        for plugin in session.config.pluginmanager.get_plugins():
            store = getattr(plugin, "_store", None)
            if store is None:
                continue
            arc_data = getattr(store, "_arc_data", None)
            if arc_data is None:
                continue
            result = {{}}
            for (path, from_line, to_line), ad in arc_data.items():
                if ad.incidental_executions > 0 or ad.deliberate_executions > 0:
                    result.setdefault(path, []).append([from_line, to_line])
            if result:
                with open("{output_path}", "w") as f:
                    json.dump(result, f)
                total = sum(len(v) for v in result.values())
                print(f"Arc dump: {{total}} arcs across {{len(result)}} files")
                return

def pytest_configure(config):
    config.pluginmanager.register(_ArcDumper(), "arc_dumper")
''')

        cmd = [
            str(pytest_bin), args.tests,
            "--coverage-stats",
            "-p", "no:xdist",
            "-q", "--tb=no",
            f"--override-ini=confcutdir={tmp}",
        ]
        print("Running tests...", file=sys.stderr)
        subprocess.run(cmd, cwd=project_dir, text=True)

    if output_path.exists():
        data = json.loads(output_path.read_text())
        total = sum(len(v) for v in data.values())
        print(f"Dumped {total} arcs across {len(data)} files to {output_path}")
    else:
        print("ERROR: arc dump not created", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
