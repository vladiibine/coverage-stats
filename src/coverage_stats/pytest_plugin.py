"""
Pytest plugin for coverage-stats.

Responsibilities:
1. Switch coverage.py dynamic context to the test node ID before each test runs.
2. Collect @covers metadata for each test.
3. Persist {test_node_id: [covered_qualnames]} to .coverage-stats-meta.json
   at the end of the session.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from coverage_stats.decorator import get_covered_targets

# Populated during the session: node_id -> list of covered qualnames (or []).
_test_covers: dict[str, list[str]] = {}


def _get_coverage() -> Any | None:
    """Return the active coverage.Coverage instance, if any."""
    try:
        import coverage as coverage_module
        return coverage_module.Coverage.current()
    except Exception:
        return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):
    """Switch coverage context to the test node ID for the duration of the test."""
    cov = _get_coverage()
    previous_context: str | None = None

    if cov is not None:
        try:
            previous_context = cov.get_data().current_context  # type: ignore[attr-defined]
        except Exception:
            previous_context = None
        try:
            cov.switch_context(item.nodeid)
        except Exception:
            pass

    # Record @covers metadata for this test.
    test_func = getattr(item, "function", None)
    if test_func is not None:
        targets = get_covered_targets(test_func)
        _test_covers[item.nodeid] = targets if targets is not None else []
    else:
        _test_covers[item.nodeid] = []

    yield  # run the test

    if cov is not None and previous_context is not None:
        try:
            cov.switch_context(previous_context)
        except Exception:
            pass


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write .coverage-stats-meta.json next to the .coverage data file."""
    # Determine output path: same directory as rootdir.
    rootdir = str(session.config.rootdir)
    meta_path = Path(rootdir) / ".coverage-stats-meta.json"

    try:
        meta_path.write_text(json.dumps(_test_covers, indent=2))
    except Exception as exc:
        session.config.pluginmanager.get_plugin("terminalreporter")  # noqa: just get ref
        print(f"\ncoverage-stats: failed to write metadata: {exc}")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "covers: mark test with the functions/classes/modules it explicitly tests "
        "(used by coverage-stats for direct vs incidental hit reporting)",
    )
