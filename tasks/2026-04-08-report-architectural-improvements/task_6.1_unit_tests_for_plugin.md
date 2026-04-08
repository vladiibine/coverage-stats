# Task 6.1 — Unit tests for `CoverageStatsPlugin`

**Priority:** P3
**Effort:** Medium
**Impact:** Medium (test coverage)

## Problem

`CoverageStatsPlugin` is tested exclusively through pytester integration tests (`tests/integration/`). These tests spin up a full pytest subprocess, which means:

- Each test takes seconds instead of milliseconds
- Edge cases (malformed xdist worker data, disabled plugin, coverage.py not installed) are hard to exercise in isolation
- Failures produce a wall of pytest output rather than a targeted assertion failure
- The plugin itself is not covered by coverage-stats (because it's the plugin doing the covering)

Individual hook behaviors that currently have no targeted tests:
- What happens if `_enabled` is `False` and every hook is called?
- What happens if `pytest_testnodedown` receives malformed JSON in `workeroutput`?
- What happens if `resolve_covers` raises for one item but not others?
- What happens if the tracer fails to install?

## Solution

After task 1.1 (split plugin.py), add unit tests for each coordinator using mock objects.

### `TracingCoordinator` tests (no pytester needed)

```python
def test_runtest_setup_resolves_covers_and_resets_ctx():
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=[])
    tracer = Mock()
    coordinator = TracingCoordinator(store, ctx, tracer)

    item = Mock(spec=pytest.Function)
    item.config._coverage_stats_ctx = ctx
    item.function._covers_refs = ()

    coordinator.pytest_runtest_setup(item)

    assert item._covers_lines == frozenset()
    assert ctx.current_phase == "setup"
    assert ctx.current_test_item is item

def test_disabled_coordinator_skips_all_hooks():
    coordinator = TracingCoordinator(enabled=False, ...)
    item = Mock()
    coordinator.pytest_runtest_setup(item)
    item.config._coverage_stats_ctx.assert_not_called()
```

### `ReportingCoordinator` tests

```python
def test_testnodedown_merges_worker_store():
    store = SessionStore()
    coordinator = ReportingCoordinator(store=store, ...)

    worker_store = SessionStore()
    worker_store.get_or_create(("/a.py", 1)).deliberate_executions = 5
    node = Mock()
    node.workeroutput = {"coverage_stats_data": json.dumps(worker_store.to_dict())}

    coordinator.pytest_testnodedown(node, error=None)

    assert store._data[("/a.py", 1)].deliberate_executions == 5

def test_testnodedown_ignores_malformed_json():
    coordinator = ReportingCoordinator(store=SessionStore(), ...)
    node = Mock()
    node.workeroutput = {"coverage_stats_data": "not-json{{{"}
    # Should warn, not raise
    with pytest.warns(UserWarning, match="coverage-stats"):
        coordinator.pytest_testnodedown(node, error=None)
```

Target: 80%+ unit-test coverage of coordinator hook methods, so integration tests only need to verify end-to-end wiring.
