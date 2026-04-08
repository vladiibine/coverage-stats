# Architectural Improvement Report: coverage-stats

**Date:** 2026-04-08
**Scope:** Full codebase review (~2,200 SLOC across 15 modules)

---

## Executive Summary

coverage-stats is a well-structured pytest plugin with enforced layering (via import-linter), clean separation between tracing/storage/reporting, and thoughtful extensibility points. The main areas for improvement are: (1) the `plugin.py` orchestrator mixes too many concerns, (2) the hot-path tracer callbacks carry avoidable overhead, (3) `report_data.py` at 758 lines is doing too much, and (4) several design choices create unnecessary coupling or fragility.

---

## 1. Structural / Maintainability Improvements

### 1.1 Split `plugin.py` into phase-based coordinators

**Current state:** `CoverageStatsPlugin` (533 lines) mixes four distinct concerns:
- Pytest hook wiring + `if not self._enabled` guards (~150 lines)
- Tracing lifecycle: start/stop/reinstall tracer, record lines (~100 lines)
- xdist topology: role detection, JSON serialization, worker merge (~100 lines)
- Coverage.py interop: pyc-cache bypass, `patch_coverage_save`, version branches (~80 lines)

**Problem:** Every new feature (e.g., a new hook, a new output format) requires touching this single class. The xdist and coverage.py interop logic obscures the core domain flow. Testing any one concern requires instantiating the full plugin.

**Recommendation:** Split into two focused classes:

```
TracingCoordinator
  owns: store, tracer, ctx
  hooks: pytest_sessionstart, pytest_collectstart, pytest_collection_finish,
         pytest_runtest_setup/call/teardown, pytest_assertion_pass

ReportingCoordinator
  owns: store ref, customization, reporters
  hooks: pytest_testnodedown (xdist merge),
         pytest_sessionfinish (flush, inject, report)
```

Extract xdist serialization into a helper (e.g., `XdistBridge`) and coverage.py interop is already in `CoveragePyInterop` but the *calling* logic (version checks, pyc-cache bypass) should move there too.

**Impact:** Each coordinator is independently testable. New hooks or interop paths don't require reading 500+ lines of context.

### 1.2 Break up `report_data.py` (758 lines)

**Current state:** This file contains:
- 7 dataclasses (`LineReport`, `FileSummary`, `IndexRowData`, `FolderNode`, `FileReport`, `CoverageReport`, `_BranchAnalysis`)
- `DefaultReportBuilder` with `build()`, `build_folder_tree()`, `_analyze_branches()`
- `CoveragePyInterop` with `compute_arcs()`, `compute_full_arcs()`, `full_arcs_for_store()`, `patch_coverage_save()`, `inject_into_coverage_py()`
- 3 backward-compat shim functions
- AST branch analysis logic (~110 lines)

**Problem:** Report building and coverage.py interop are unrelated concerns sharing a file. `CoveragePyInterop` duplicates AST walking logic from `_analyze_branches`. The dataclasses are consumed by multiple reporters but live next to the builder.

**Recommendation:**
- `reporters/models.py` — all dataclasses (`LineReport`, `FileSummary`, `FolderNode`, etc.)
- `reporters/report_data.py` — `DefaultReportBuilder` only
- `reporters/coverage_py_interop.py` — `CoveragePyInterop` (already its own concern)
- `reporters/branch_analysis.py` — shared AST branch walking, used by both builder and interop

This also eliminates the TODO comment at line 745 about the backward-compat shims: once the dataclasses are in their own module, the shims can be removed from `report_data.py` entirely (tests import from `models.py` directly).

### 1.3 Remove `assert_counter.py`

**Current state:** 18-line file that re-exports `record_assertion` and `distribute_asserts` from `ProfilerContext`. The actual logic lives in `profiler.py`.

**Problem:** It's a dead indirection. The import-linter layer (`coverage_stats.assert_counter`) exists only because this file exists; removing it simplifies the layer graph.

**Recommendation:** Delete `assert_counter.py`, update import-linter contracts, update any tests that import from it.

### 1.4 `FolderNode` aggregation methods are O(n*d) on every call

**Current state:** `FolderNode` has 9 `agg_*` methods that each recursively traverse the entire subtree. `to_index_row()` calls 9 of them, meaning the tree is traversed 9 times per folder node.

**Problem:** For a codebase with 500 files in 50 folders, rendering the index page does ~450 recursive traversals (9 aggregations x 50 nodes). This is O(n*d*k) where n=files, d=depth, k=metrics.

**Recommendation:** Compute all aggregates in a single bottom-up pass and cache them on the node:

```python
@dataclass
class FolderNode:
    path: str
    subfolders: dict[str, FolderNode]
    files: list[FileSummary]
    _agg: _FolderAggregates | None = None  # cached after compute_aggregates()

    def compute_aggregates(self) -> _FolderAggregates:
        """Single bottom-up pass; call once after tree is built."""
        ...
```

This reduces index rendering from O(n*d*k) to O(n).

---

## 2. Performance Improvements

### 2.1 Hot-path: reduce attribute lookups in tracer callbacks

The tracer callback fires on **every line executed** during tests. Even small overheads compound into measurable slowdowns.

**Current `_make_local_trace` inner function (profiler.py:280-303):**
```python
def local(frame, event, arg):
    nonlocal current_prev
    if current_prev is not None:
        current_prev = current_prev(frame, event, arg)
    if event == "line":
        ctx = self._context          # attribute lookup on self
        lineno = frame.f_lineno
        key = (filename, lineno)
        if ctx.current_phase == "call" and ctx.current_test_item is not None:
            ld = self._store.get_or_create(key)   # attribute lookup on self
            covers_lines = getattr(ctx.current_test_item, "_covers_lines", frozenset())  # getattr every line
            ...
```

**Optimizations:**
1. **Capture `_context` and `_store` as closure variables** instead of looking them up via `self` on every call. `self._context` and `self._store` never change after `__init__`.
2. **Cache `covers_lines` per test** rather than calling `getattr(ctx.current_test_item, "_covers_lines", frozenset())` on every line event. The covers_lines for a test are set once in `pytest_runtest_setup` and never change. Store it on `ProfilerContext` (e.g., `ctx.current_covers_lines`) and set it once per test.
3. **Skip the `event == "line"` check** in the local tracer. Python only calls the local trace function for `line`, `return`, and `exception` events. For `return` and `exception` events, doing the dict lookup is cheap and harmless. Removing the branch saves one comparison per line event. Alternatively, the function can be registered for line events only if using a framework that supports event filtering.

**Estimated impact:** 15-25% reduction in per-line overhead based on typical Python attribute lookup costs (~50ns each, millions of calls).

### 2.2 Hot-path: use `__slots__` on `LineData`

**Current state:** `LineData` is a regular dataclass with a `__dict__` per instance.

**Problem:** Each `LineData` instance carries a `__dict__` (~200 bytes). For a 10k-line codebase with 30% coverage, that's 3,000 instances = ~600KB of pure dict overhead. More importantly, attribute access on `__dict__`-based objects is slower than slot-based access.

**Recommendation:**
```python
@dataclass(slots=True)  # Python 3.10+
class LineData:
    ...
```

For Python 3.9 compat, add `__slots__` manually. This reduces memory by ~40% per instance and speeds up attribute access in the hot path (the tracer increments `ld.deliberate_executions` or `ld.incidental_executions` on every line event).

### 2.3 `SessionStore.get_or_create` — use `setdefault`

**Current state:**
```python
def get_or_create(self, key):
    if key not in self._data:
        self._data[key] = LineData()
    return self._data[key]
```

This performs two dict lookups on a cache miss (one for `in`, one for `[]`).

**Recommendation:** In Python, `dict.setdefault` or `defaultdict` with a factory are both single-lookup operations:

```python
# Option A: defaultdict (zero-cost on hit, single lookup on miss)
self._data: defaultdict[tuple[str, int], LineData] = defaultdict(LineData)

# Then get_or_create becomes:
def get_or_create(self, key):
    return self._data[key]
```

This is a micro-optimization but it's in the hottest path of the entire plugin.

### 2.4 `executable_lines.py` — cache parsed ASTs

**Current state:** `get_executable_lines(path)` reparses the source file from disk every time it's called. `_analyze_branches` in `report_data.py` *also* parses the same file. `CoveragePyInterop.compute_arcs` parses it a third time.

**Problem:** For a file with 1,000 lines, `ast.parse` + `ast.walk` takes ~1-5ms. Across 100 files, that's 300-1500ms of redundant parsing.

**Recommendation:** Introduce a simple file-level AST cache (dict keyed by path, cleared at session end). Pass it through the report builder so `get_executable_lines`, `_analyze_branches`, and `compute_arcs` all share the same parsed tree. Alternatively, combine these into a single `FileAnalysis` object that parses once and exposes executable lines, branch info, and arcs.

### 2.5 `_in_scope` — avoid string operations on every call

**Current state:**
```python
def _in_scope(self, filename: str) -> bool:
    return any(
        filename == d or filename.startswith(d + "/")
        for d in self._context.source_dirs
    )
```

This creates a new string `d + "/"` on every call for every source dir.

**Recommendation:** Precompute the suffixed dirs once in `__init__`:
```python
self._source_prefixes = [(d, d + "/") for d in context.source_dirs]

def _in_scope(self, filename):
    return any(filename == d or filename.startswith(p) for d, p in self._source_prefixes)
```

Small savings per call, but this runs once per unique file, and it's trivial to fix.

---

## 3. Extensibility Improvements

### 3.1 Make `_analyze_branches` pluggable

**Current state:** Branch analysis is a protected method on `DefaultReportBuilder`. Users who want different branch semantics (e.g., handling `try/except`, `with` statements, or comprehension short-circuits) must subclass `DefaultReportBuilder` and override the entire method.

**Problem:** The method is 110 lines long with interleaved if/while/for and match-case logic. Overriding it means copying and modifying a large block.

**Recommendation:** Extract branch analysis into a `BranchAnalyzer` protocol with a default implementation. Each branch type (if/while/for, match-case) can be a separate method, making it practical to override just one:

```python
class BranchAnalyzer(Protocol):
    def analyze(self, path: str, lines: dict[int, LineData]) -> _BranchAnalysis: ...

class DefaultBranchAnalyzer:
    def analyze(self, path, lines):
        ...  # delegates to _analyze_if_while_for() and _analyze_match()
    
    def _analyze_if_while_for(self, tree, lines, partial, counters): ...
    def _analyze_match(self, tree, lines, partial, counters): ...
```

Add `branch_analyzer` to `CoverageStatsCustomization` so users can swap it.

### 3.2 Deduplicate branch-walking between report builder and coverage.py interop

**Current state:** `DefaultReportBuilder._analyze_branches` and `CoveragePyInterop.compute_arcs` both walk the AST for `if/while/for/match` nodes with nearly identical logic. The difference is that one counts arcs and detects partial coverage, while the other produces `(from, to)` arc pairs.

**Recommendation:** Unify into a shared `BranchWalker` that yields branch descriptors:

```python
@dataclass
class BranchDescriptor:
    node_line: int
    true_target: int
    false_target: int | None
    true_taken: bool
    false_taken: bool
    deliberate_true: bool
    deliberate_false: bool
    incidental_true: bool
    incidental_false: bool
```

Both `_analyze_branches` and `compute_arcs` consume these descriptors but interpret them differently. This eliminates ~60 lines of duplicated AST walking.

### 3.3 Event-based architecture for test lifecycle

**Current state:** The plugin directly calls `resolve_covers`, `ctx.distribute_asserts`, `_flush_pre_test_lines` from hook methods. Adding a new per-test action (e.g., recording test duration per line, or per-line assertion tracking) requires modifying `CoverageStatsPlugin`.

**Recommendation (future):** Introduce lightweight lifecycle events that observers can subscribe to:

```python
class TestLifecycleEvent:
    TEST_SETUP = "test_setup"
    TEST_CALL_START = "test_call_start"
    TEST_TEARDOWN = "test_teardown"
    SESSION_FINISH = "session_finish"
```

This is a larger change and only worth doing if/when more per-test behaviors are needed. For now, the `CoverageStatsCustomization` entry point provides sufficient extensibility.

---

## 4. Correctness / Robustness Improvements

### 4.1 Coverage.py interop version coupling

**Current state:** The interop code assumes `coverage.Coverage.current()` exists, `data.has_arcs()` works, and `data.add_lines()`/`data.add_arcs()` accept specific formats. These are not part of coverage.py's public API.

**Problem:** A coverage.py major release could break any of these. The current code has no version guard.

**Recommendation:** Pin a minimum coverage.py version in the interop and add a try/except with a clear warning:

```python
def inject_into_coverage_py(self, store):
    try:
        import coverage
        if not hasattr(coverage.Coverage, 'current'):
            warnings.warn("coverage-stats: unsupported coverage.py version")
            return
        ...
    except Exception as exc:
        warnings.warn(f"coverage-stats: coverage.py interop failed: {exc}")
```

Also consider adding integration tests that pin specific coverage.py versions to catch regressions.

### 4.2 Tracer displacement detection

**Current state:** `LineTracer.start()` checks `current is self._installed_fn` to detect if we're still on top. But there's no detection for the case where a *third* tracer displaces us mid-test.

**Problem:** If another plugin installs a tracer during test execution, coverage-stats silently stops recording. There's no warning.

**Recommendation:** Add a periodic check (e.g., every N line events) or at least check at `pytest_runtest_teardown` that the tracer is still installed:

```python
def pytest_runtest_teardown(self, item, nextitem):
    if self._tracer and not self._tracer.is_active():
        warnings.warn("coverage-stats: tracer was displaced during test execution")
```

### 4.3 `MonitoringLineTracer` tool ID fallback

**Current state:** Tool IDs are tried in order `(4, 5, 3, 2)`. IDs 2 and 3 are reserved for "profiler" and "optimizer" by CPython convention.

**Problem:** Claiming a reserved ID may conflict with future CPython features or third-party tools that legitimately use those IDs.

**Recommendation:** Only fall back to reserved IDs with an explicit warning, or fail loudly:

```python
for tool_id in (4, 5):
    try:
        monitoring.use_tool_id(tool_id, "coverage-stats")
        break
    except ValueError:
        continue
else:
    warnings.warn(
        "coverage-stats: tool IDs 4-5 unavailable; "
        "falling back to reserved IDs (may conflict with other tools)"
    )
    for tool_id in (3, 2):
        ...
```

### 4.4 Thread safety

**Current state:** `SessionStore._data` is a plain dict. `ProfilerContext` fields (`current_test_lines`, `current_assert_count`) are mutated without locks.

**Problem:** While pytest typically runs tests sequentially in a single process (xdist uses separate processes), some test setups use threads (e.g., `pytest-parallel`, tests that spawn threads). Concurrent mutations to `_data` or `current_test_lines` would corrupt data.

**Recommendation:** Document the single-threaded assumption explicitly. If thread safety becomes needed, `SessionStore` can use a `threading.Lock` around `get_or_create`, and `ProfilerContext` can use thread-local storage for per-test state.

---

## 5. Code Quality Improvements

### 5.1 `store._data` is accessed directly by consumers

**Current state:** `DefaultReportBuilder.build()` reads `store._data.items()` directly. `CoveragePyInterop` also reads `store._data`. The underscore prefix signals "private" but it's used everywhere.

**Recommendation:** Either make it public (`store.data`) or add iteration methods:

```python
class SessionStore:
    def items(self) -> Iterator[tuple[tuple[str, int], LineData]]:
        return iter(self._data.items())
    
    def files(self) -> dict[str, dict[int, LineData]]:
        """Group line data by file path."""
        ...
```

### 5.2 Eliminate `getattr(ctx.current_test_item, "_covers_lines", frozenset())`

This pattern appears in 3 places (both tracer callbacks and `distribute_asserts`). It's fragile — if `resolve_covers` didn't run, the fallback silently treats everything as incidental.

**Recommendation:** Store `covers_lines` on `ProfilerContext` directly:

```python
@dataclass
class ProfilerContext:
    current_covers_lines: frozenset[tuple[str, int]] = frozenset()
```

Set it in `pytest_runtest_setup` alongside `current_test_item`. This makes the data flow explicit and eliminates the `getattr` in the hot path.

### 5.3 Type annotations for `_XdistWorkerNode`

**Current state:** `_XdistWorkerNode` is a minimal `Protocol` with `workeroutput: dict[str, str]`. But `pytest_testnodedown` also calls `getattr(node, "workeroutput", {})`, bypassing the protocol.

**Recommendation:** Trust the protocol or don't use it. Since xdist guarantees `workeroutput` on worker nodes, the `getattr` fallback is unnecessary defensiveness.

---

## 6. Testing Improvements

### 6.1 No unit tests for `CoverageStatsPlugin` itself

**Current state:** The plugin is only tested via pytester integration tests. Individual hook behaviors (e.g., "what happens if `_enabled` is False?", "what if xdist worker data is malformed?") are not tested in isolation.

**Recommendation:** After the plugin.py split (1.1), add unit tests for each coordinator. The tracing coordinator can be tested with a mock store and a mock tracer. The reporting coordinator can be tested with a pre-populated store.

### 6.2 No performance benchmarks

**Current state:** The TODO mentions "check that performance is not seriously degraded" (marked done), but there are no persistent benchmarks.

**Recommendation:** Add a simple benchmark test (e.g., trace 10,000 line events, measure wall time) that runs in CI. This catches regressions from seemingly innocent changes (like adding an attribute lookup to the hot path).

---

## 7. Priority Matrix

| Improvement | Effort | Impact | Priority |
|---|---|---|---|
| 2.1 Reduce hot-path attribute lookups | Low | High (perf) | **P0** |
| 2.2 `__slots__` on `LineData` | Low | Medium (perf + memory) | **P0** |
| 5.2 Move `covers_lines` to `ProfilerContext` | Low | Medium (perf + clarity) | **P0** |
| 2.3 `defaultdict` for `SessionStore` | Low | Low-Medium (perf) | **P1** |
| 2.5 Precompute `_in_scope` prefixes | Low | Low (perf) | **P1** |
| 1.3 Remove `assert_counter.py` | Low | Low (simplicity) | **P1** |
| 1.4 Single-pass `FolderNode` aggregation | Low | Medium (perf for large codebases) | **P1** |
| 1.2 Break up `report_data.py` | Medium | High (maintainability) | **P1** |
| 5.1 Public iteration API on `SessionStore` | Low | Medium (encapsulation) | **P2** |
| 1.1 Split `plugin.py` | Medium-High | High (maintainability + testability) | **P2** |
| 2.4 Cache parsed ASTs | Medium | Medium (perf for reporting phase) | **P2** |
| 3.2 Deduplicate branch walking | Medium | Medium (maintainability) | **P2** |
| 4.1 Coverage.py version guarding | Low | Medium (robustness) | **P2** |
| 3.1 Pluggable branch analyzer | Medium | Medium (extensibility) | **P3** |
| 4.2 Tracer displacement detection | Low | Low (diagnostics) | **P3** |
| 4.3 Tool ID fallback warnings | Low | Low (correctness) | **P3** |
| 6.1 Unit tests for plugin | Medium | Medium (test coverage) | **P3** |
| 6.2 Performance benchmarks | Medium | Medium (regression prevention) | **P3** |
| 3.3 Event-based lifecycle | High | Low (premature unless needed) | **P4** |
| 4.4 Thread safety docs | Low | Low (documentation) | **P4** |

---

## Summary

The codebase is in good shape for its maturity. The import-linter contracts, the `CoverageStatsCustomization` entry point, and the reporter protocol show architectural foresight. The highest-value changes are:

1. **Quick wins (P0):** Optimize the tracer hot path — move `covers_lines` to `ProfilerContext`, capture store/context as closure variables, add `__slots__` to `LineData`. These are low-effort, high-impact changes.

2. **Structural cleanup (P1-P2):** Break up `report_data.py`, split `plugin.py` into coordinators, remove `assert_counter.py`. These improve maintainability without changing behavior.

3. **Robustness (P2):** Guard against coverage.py API changes, deduplicate branch analysis logic.

The plugin's core design — trace per line, classify as deliberate/incidental, distribute asserts at teardown, build reports from a flat store — is sound and doesn't need rethinking.
