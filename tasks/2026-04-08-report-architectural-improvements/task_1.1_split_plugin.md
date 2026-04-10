# Task 1.1 — Split `plugin.py` into phase-based coordinators

**Priority:** P2
**Effort:** Medium-High
**Impact:** High (maintainability + testability)
**Status:** done

## Problem

`CoverageStatsPlugin` (533 lines) mixes four distinct concerns in a single class:

| Concern | Approx. lines | Examples |
|---|---|---|
| Pytest hook wiring + guards | ~150 | `if not self._enabled: return` on every hook |
| Tracing lifecycle | ~100 | start/stop/reinstall tracer, record pre-test lines |
| xdist topology | ~100 | role detection, JSON serialization, worker merge |
| Coverage.py interop | ~80 | pyc-cache bypass, `patch_coverage_save`, version branches |

Consequences:
- Every new feature requires reading 500+ lines to find the right hook
- xdist and coverage.py interop logic obscures the core domain flow
- Unit-testing any one concern requires instantiating the entire plugin
- The `if _is_xdist_controller` / `if _is_xdist_worker` conditionals appear in multiple hooks, duplicating topology decisions

## Solution

Split into two coordinator classes registered as separate pytest plugins:

### `TracingCoordinator`
Owns: `store`, `tracer`, `ctx`

Hooks:
- `pytest_sessionstart` (trylast) — install tracer
- `pytest_collectstart` (trylast) — reinstall tracer before each module
- `pytest_collection_finish` (trylast) — reinstall after coverage.py's stop/start cycle; restore pyc hook
- `pytest_runtest_setup` — resolve `@covers`, reset ctx
- `pytest_runtest_call` — advance phase to "call"
- `pytest_runtest_teardown` — distribute asserts, reset ctx
- `pytest_assertion_pass` — increment assert count

Does NOT handle xdist worker serialization or report writing.

### `ReportingCoordinator`
Owns: reference to `store`, `customization`, `reporters`

Hooks:
- `pytest_testnodedown` (optionalhook) — merge xdist worker stores
- `pytest_sessionfinish` (tryfirst) — flush pre-test lines, inject into coverage.py, write reports

### Shared helpers (module-level functions or a thin `XdistBridge`)
- `_is_xdist_worker(config)`, `_is_xdist_controller(config)` — already module-level, keep as-is
- `_flush_pre_test_lines(ctx, store)` — already module-level, keep as-is

### `pytest_configure` (module-level)
Instantiates both coordinators, wires them together (sharing the same `store`), registers both with the plugin manager. The topology check (worker/controller/single) decides which coordinators to instantiate:
- xdist controller: `ReportingCoordinator` only (no tracing)
- xdist worker: `TracingCoordinator` only (no reporting)
- single-process: both

**Migration approach:**
1. Create `_tracing.py` with `TracingCoordinator` — move hooks, test with existing integration tests
2. Create `_reporting.py` with `ReportingCoordinator` — move remaining hooks
3. Slim `plugin.py` down to `pytest_addoption`, `pytest_configure`, and the two coordinator imports
4. Update `pyproject.toml` entry point (still points to `coverage_stats.plugin`)
5. Update import-linter contracts for the new internal modules

**Note:** The pyc-cache bypass (`_read_pyc = None`) currently lives in `pytest_configure` and is restored in `pytest_collection_finish`. This is coverage.py-interop logic — consider moving it to `TracingCoordinator.__init__` and the `pytest_collection_finish` hook, or to a `CoveragePyInterop` setup method.

# Vlad's comments
1. After instantiation of certain objects, there's a lot of private attribute setting; That's what the `__init__` methods are for. Move the setting of private variables to the initializer
2. TracingCoordinator and ReportingCoordinator - Let's not instantiate them directly, and instead load them dymanically like we load all kinds of other classes. Their fully qualified class names should be set on the Customization class, and there should be a method to create an instance of each (it's possible that this method )
3. unrelated: the customization class, on instantiation, should receive as much context as possible. In this case, `config` is the only parameter that we can pass - so let's do that!
4. unrelated: we should get rid of as many free functions as possible. Ideally, just the pytest plugin functions should be defined at module-level. Every other function should actually live on a class - so users can customize them by providing overrides