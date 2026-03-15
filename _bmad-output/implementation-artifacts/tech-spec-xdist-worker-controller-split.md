---
title: 'xdist Worker/Controller Split'
type: 'feature'
created: '2026-03-15'
status: 'done'
baseline_commit: '35054f6f73de69e9ac35cfe92a3a75cbbfa56205'
context:
  - _bmad-output/planning-artifacts/architecture.md
---

# xdist Worker/Controller Split

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** When pytest-xdist distributes tests across worker processes, each worker holds its own isolated `SessionStore`; the controller never receives that data, so reports are never written and coverage is silently incomplete.

**Approach:** Detect worker vs controller via duck-typing on `config.workerinput` / `pluginmanager.hasplugin("xdist")`; workers serialize their store into `config.workeroutput["coverage_stats_data"]` at session end; the controller accumulates via `pytest_testnodedown` and calls reporters once at its own `pytest_sessionfinish`. When xdist is absent the existing single-process path is unchanged.

## Boundaries & Constraints

**Always:**
- `from __future__ import annotations` at the top of every modified module
- Two module-level helper functions in `plugin.py` (canonical names from architecture doc):
  ```python
  def _is_xdist_worker(config) -> bool:
      return hasattr(config, "workerinput")

  def _is_xdist_controller(config) -> bool:
      return not _is_xdist_worker(config) and config.pluginmanager.hasplugin("xdist")
  ```
- In `pytest_configure`, when `_is_xdist_controller(config)` is True: create `SessionStore` only — no `ProfilerContext`, no `LineTracer`; set `config._coverage_stats_ctx = None`; set `plugin._store = store`; `plugin._tracer = None`; do not call `tracer.start()`
- In `pytest_sessionfinish`, worker branch (`_is_xdist_worker(session.config)`): stop tracer, write `json.dumps(self._store.to_dict())` to `session.config.workeroutput["coverage_stats_data"]`, then return — do NOT call any reporter
- In `pytest_sessionfinish`, non-worker branch (controller or no-xdist): unchanged — stop tracer if present, then call reporters
- Add `pytest_testnodedown(self, node, error) -> None` to `CoverageStatsPlugin`: guard with `if not self._enabled: return`; read `node.workeroutput.get("coverage_stats_data")`; if present, `import json` + `SessionStore.from_dict(json.loads(raw))` then `self._store.merge(worker_store)`
- stdlib + pytest only — never `import xdist`; rely solely on duck-typing (`workerinput`, `workeroutput`, `hasplugin`)

**Ask First:**
- If `pytest_testnodedown` fires on a node whose `workeroutput` key is absent (worker crashed before serialising) and silent data loss is unacceptable — ask whether to emit a warning

**Never:**
- Import from the `xdist` package directly
- Call reporters from a worker's `pytest_sessionfinish`
- Modify `store.py`
- Change signatures of existing hook methods
- Start `LineTracer` on the controller

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| xdist absent, single process | `not hasattr(config, "workerinput")`, xdist plugin not registered | Existing flow unchanged; reporters called from `pytest_sessionfinish` | — |
| xdist worker | `hasattr(config, "workerinput") == True` | Tracer starts; at session end, store serialized into `workeroutput["coverage_stats_data"]`; reporters NOT called | — |
| xdist controller | `hasplugin("xdist") == True`, no `workerinput` | No tracer started; each worker's payload merged via `pytest_testnodedown`; reporters called once at `pytest_sessionfinish` | — |
| Worker crash / missing key | `node.workeroutput` has no `"coverage_stats_data"` | `pytest_testnodedown` silently skips (no error) | `dict.get` returns `None` → guarded |
| Two workers, overlapping lines | Both workers trace `(foo.py, 10)` | Merged store sums both workers' counts additively | — |
| `--coverage-stats` absent | Plugin disabled | No xdist hooks fire; no-op as before | — |

</frozen-after-approval>

## Code Map

- `src/coverage_stats/plugin.py` — add `_is_xdist_worker`, `_is_xdist_controller`; update `pytest_configure`; add `pytest_testnodedown`; update `pytest_sessionfinish`
- `src/coverage_stats/store.py` — read-only reference; `to_dict` / `from_dict` / `merge` already implemented
- `tests/unit/test_xdist_split.py` — unit tests for detection helpers, `pytest_testnodedown`, worker/controller session-finish branching
- `tests/integration/test_plugin_xdist.py` — pytester integration test (skipped if xdist absent)

## Tasks & Acceptance

**Execution:**
- [ ] `src/coverage_stats/plugin.py` -- ADD -- `_is_xdist_worker(config)` and `_is_xdist_controller(config)` module-level helpers; update `pytest_configure` to skip tracer setup on controller; add `pytest_testnodedown` hook; update `pytest_sessionfinish` to branch on worker vs non-worker
- [ ] `tests/unit/test_xdist_split.py` -- CREATE -- tests: `_is_xdist_worker` true/false; `_is_xdist_controller` true/false; `pytest_testnodedown` merges correctly; `pytest_testnodedown` skips missing key; worker `pytest_sessionfinish` populates `workeroutput` and skips reporters; controller configure creates store but no tracer
- [ ] `tests/integration/test_plugin_xdist.py` -- CREATE -- pytester test: `pytest.importorskip("xdist")`; run a two-worker session; assert merged JSON output sums both workers' counts

**Acceptance Criteria:**
- Given `config` with `workerinput` attribute, when `_is_xdist_worker(config)` is called, then it returns `True`
- Given `config` without `workerinput` and xdist plugin registered, when `_is_xdist_controller(config)` is called, then it returns `True`
- Given worker `pytest_sessionfinish`, when it runs, then `config.workeroutput["coverage_stats_data"]` contains a JSON string and no report files are written
- Given controller `pytest_testnodedown` with two nodes each carrying `coverage_stats_data`, when both are processed, then `self._store._data` contains the additive sum of both workers' line counts
- Given `pytest_testnodedown` with a node whose `workeroutput` has no `coverage_stats_data` key, when it runs, then no exception is raised
- Given `pytest --coverage-stats -n2` with xdist installed, when tests finish, then the JSON report reflects data from both workers

## Design Notes

**Worker detection via duck-typing:**
xdist sets `config.workerinput` on worker processes before any hooks run. The controller has no such attribute. `hasplugin("xdist")` is True only if xdist is installed. This pair cleanly covers all three cases (worker / controller / no-xdist) without importing xdist internals.

**Controller configure path:**
```python
if _is_xdist_controller(config):
    from coverage_stats.store import SessionStore
    store = SessionStore()
    config._coverage_stats_ctx = None
    plugin._store = store
    plugin._tracer = None
    config.pluginmanager.register(plugin, "coverage-stats-plugin")
    return
```

**Worker sessionfinish serialization:**
```python
import json
session.config.workeroutput["coverage_stats_data"] = json.dumps(self._store.to_dict())
return  # reporters must not be called on worker
```

## Verification

**Commands:**
- `.venv/bin/pytest tests/unit/test_xdist_split.py -v` -- expected: all tests pass
- `.venv/bin/ruff check src/coverage_stats/plugin.py` -- expected: exit 0
- `.venv/bin/pytest tests/integration/test_plugin_xdist.py -v` -- expected: either all pass (xdist installed) or all skipped (xdist absent)
