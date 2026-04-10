"""Benchmarks for SessionStore throughput.

Run with:
    nox -s benchmark
"""
from __future__ import annotations

import pytest

from coverage_stats.store import SessionStore


_FILE = "/src/module.py"
_N = 1_000


@pytest.fixture
def cold_store():
    return SessionStore()


@pytest.fixture
def warm_store():
    """Store pre-populated with N keys so get_or_create always hits."""
    store = SessionStore()
    for i in range(_N):
        store.get_or_create((_FILE, i))
    return store


def test_get_or_create_cold(benchmark, cold_store):
    """get_or_create with N distinct keys never seen before (all misses).

    Exercises the defaultdict __missing__ path and LineData construction.
    """
    keys = [(_FILE, i) for i in range(_N)]

    def run():
        for key in keys:
            cold_store.get_or_create(key)

    benchmark(run)


def test_get_or_create_warm(benchmark, warm_store):
    """get_or_create with N keys that already exist (all hits).

    Exercises the common hot-path: the tracer calls this for every in-scope
    line event, and most keys are already present after the first test.
    """
    keys = [(_FILE, i) for i in range(_N)]

    def run():
        for key in keys:
            warm_store.get_or_create(key)

    benchmark(run)


def test_files_grouping(benchmark, warm_store):
    """files() groups all entries by path into a dict[str, dict[int, LineData]].

    Called once per reporting run per worker, but exercises the full store scan.
    """
    benchmark(warm_store.files)


def test_store_merge(benchmark):
    """merge() combines two stores of equal size.

    Relevant for xdist: the controller merges one store per worker.
    """
    a = SessionStore()
    b = SessionStore()
    for i in range(_N):
        a.get_or_create((_FILE, i)).incidental_executions = 1
        b.get_or_create((_FILE, i)).deliberate_executions = 1

    def run():
        # Create fresh stores each iteration so the merge doesn't accumulate.
        src = SessionStore()
        dst = SessionStore()
        for i in range(_N):
            src.get_or_create((_FILE, i)).incidental_executions = 1
            dst.get_or_create((_FILE, i)).deliberate_executions = 1
        dst.merge(src)

    benchmark(run)
