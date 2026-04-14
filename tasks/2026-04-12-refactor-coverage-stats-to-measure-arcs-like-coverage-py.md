# Task: Refactor coverage-stats to measure arcs like coverage.py

## Problem Statement

coverage-stats and coverage.py produce different branch coverage numbers because
they use fundamentally different measurement approaches:

- **coverage.py** records actual `(from_line, to_line)` arc transitions as code
  executes. Branch coverage is computed directly from observed arcs.
- **coverage-stats** records per-line execution counts, then uses AST heuristics
  to *infer* which branches were taken. This is inherently approximate.

### Evidence: httpx comparison (Python 3.9, solo runs — no tracer conflict)

| File | cov % | cs % | Root cause |
|------|-------|------|------------|
| `__init__.py` | 100.0000 | 100.0000 | converged (after exit-scope fix) |
| `_client.py` | 98.6446 (133/142 br) | 98.4940 (132/142 arcs) | heuristic false negative |
| `_config.py` | 100.0000 (92/92 stmts) | 99.0566 (91/92 stmts) | multi-line statement gap |
| `_multipart.py` | 99.1342 (68/70 br) | 99.1342 (68/70 arcs) | converged (after exit-scope fix) |

### Specific failure modes of the heuristic approach

**1. Comprehension/generator inflation (unfixable with line counts)**

```python
if allow_env_proxies:            # line 243: 397 executions
    return {                      # line 244: 618 executions (comprehension inflates)
        key: ... for key, ...
    }
return {}                         # line 248: 211 executions (clearly taken!)
```

Heuristic: `false_taken = if_count > body_count` → `397 > 618` → **False**.
Reality: line 248 was executed 211 times. The false branch was clearly taken.
No execution-count heuristic can fix this — comprehensions inflate body counts.

**2. Multi-line statement tracing gap**

```python
return (           # line 239: 0 trace events (Python skips this line)
    None           # line 240: 72 trace events
    if self.auth is None
    ...
)
```

Python's tracer doesn't fire a line event for the `return (` line. coverage.py
consolidates multi-line statements (if any line in the span was traced, the
statement is covered). coverage-stats doesn't do this consolidation.

**3. Exit-scope arc mismatches (partially fixed)**

When an `if`/`for` is the last statement in a function, BranchWalker resolves
the false target to the next method in the class (positive line), but
coverage.py models this as a negative exit-scope arc `(line, -scope_line)`.
We added fallback logic for this, but it's a band-aid over the core issue.

**4. Constructs BranchWalker doesn't handle**

`try/except`, `with` statements, and other control flow constructs generate
arcs in coverage.py but are invisible to BranchWalker (which only handles
`if/while/for/match`). This is an open-ended problem — every new construct
requires new heuristics.

### Previous findings (from tasks/ directory)

Earlier investigations documented additional issues:
- `while True:` generates 0 arcs in coverage.py but BranchWalker counted 2
  (fixed by skipping constant-truthy While nodes)
- `async for` was missing from BranchWalker (fixed by adding AsyncFor)
- Single-excluded-target branches counted as 1-arc instead of 0 (fixed)
- Tracer installation timing: on Python < 3.12, coverage.py's tracer starts
  before coverage-stats, so coverage.py captures module-level code that
  coverage-stats misses entirely

## Proposed Solution: Arc-Level Tracing

Replace the line-count + heuristic approach with actual arc recording in the
tracer. The `sys.settrace` callback already sees line events in sequence — by
tracking the previous `(file, line)` at each event, we can record actual arc
transitions with minimal additional overhead.

This eliminates **all** heuristic-based branch detection and makes coverage-stats
use the same measurement methodology as coverage.py.

## Architecture Overview (Current)

### Data flow today

```
sys.settrace / sys.monitoring
        │
        ▼
   LineTracer / MonitoringLineTracer
   (records line executions)
        │
        ▼
   SessionStore
   key: (path, lineno)
   val: LineData {incidental_executions, deliberate_executions, ...}
        │
        ▼
   DefaultReportBuilder._analyze_branches()
   (AST walk + heuristics to infer branch coverage)
        │
        ▼
   _BranchAnalysis {arcs_total, arcs_covered, ...}
```

### Key files

| File | Role | Lines |
|------|------|-------|
| `src/coverage_stats/profiler.py` | Tracers (LineTracer, MonitoringLineTracer) | ~350 |
| `src/coverage_stats/store.py` | SessionStore, LineData | ~125 |
| `src/coverage_stats/reporters/report_data.py` | Report builder, `_analyze_branches` | ~290 |
| `src/coverage_stats/reporters/branch_analysis.py` | BranchWalker, BranchDescriptor | ~180 |
| `src/coverage_stats/reporters/models.py` | _BranchAnalysis, LineReport, etc. | ~60 |
| `src/coverage_stats/executable_lines.py` | ExecutableLinesAnalyzer, static_arcs | ~330 |

### Tracer details

**LineTracer** (Python < 3.12, `sys.settrace`):
- Global trace function installed via `sys.settrace(self._trace)`
- Returns per-frame local trace functions for in-scope files
- On "line" event: resolves filename, checks scope, calls `store.get_or_create((path, lineno))`, increments `deliberate_executions` or `incidental_executions`
- Chains to previous tracer (e.g., coverage.py's CTracer) for compatibility
- Scope checking cached per filename to amortize `Path.resolve()` cost

**MonitoringLineTracer** (Python 3.12+, `sys.monitoring`):
- Registers for `monitoring.events.LINE` via tool ID
- Same recording logic as LineTracer
- No chaining needed — sys.monitoring supports multiple independent tools

**ProfilerContext.distribute_asserts()**: Called at test end. Walks
`current_test_lines` and distributes assert counts to each LineData, split
by deliberate vs incidental.

### Store details

**LineData** fields:
- `incidental_executions: int`
- `deliberate_executions: int`
- `incidental_asserts: int`
- `deliberate_asserts: int`
- `incidental_tests: int`
- `deliberate_tests: int`
- `incidental_test_ids: set[str]`
- `deliberate_test_ids: set[str]`

**SessionStore**: `defaultdict[tuple[str, int], LineData]` keyed by `(path, lineno)`.

### Branch analysis details

**BranchWalker.walk_branches()**: AST walk yielding `BranchDescriptor` per
`if/while/for/async for/match` node. Determines `true_taken`/`false_taken`
via execution-count heuristics:
- `true_taken = body_count > 0`
- `false_taken = if_count > body_count` (for no-else case)
- `false_taken = _count(orelse_lineno) > 0` (for explicit else)

**`_analyze_branches()`** has two paths:
1. **With coverage.py** (`static_arcs is not None`): Uses `static_arcs` for
   the denominator, BranchWalker's `true_taken`/`false_taken` for the numerator.
   Matches BranchDescriptors against static arcs via target line numbers.
2. **Without coverage.py**: Uses BranchWalker's `arc_count` for denominator,
   same heuristics for numerator.

## Implementation Plan

### Phase 1: Record arcs in the tracer

**Goal:** Record `(from_line, to_line)` transitions in addition to line counts.

**Changes to profiler.py:**

In both `LineTracer._make_local_trace` and `MonitoringLineTracer._monitoring_line`:

- Add a per-file `prev_line` tracker. For LineTracer this can be a local
  variable in the per-frame closure (`_make_local_trace`). For
  MonitoringLineTracer, this needs to be a dict keyed by code object or
  filename (since there's no per-frame state).
- On each "line" event, before updating `prev_line`, record the arc
  `(prev_line, current_line)` if both are in-scope and in the same file.
- On "return" event (LineTracer only — it gets return events), record an
  exit arc. This can be modeled as `(last_line, -1)` or similar.
- On "call" event, reset `prev_line` for the new frame.

**Important consideration:** The tracer must handle the deliberate/incidental
split for arcs, not just lines. An arc should carry the same
deliberate/incidental classification as its execution context.

**Changes to store.py:**

Add an `ArcData` class (similar to `LineData`) and extend `SessionStore`:

```python
@dataclass
class ArcData:
    incidental_executions: int = 0
    deliberate_executions: int = 0
```

Extend `SessionStore` with a parallel dict for arcs:

```python
_arc_data: defaultdict[tuple[str, int, int], ArcData]
# key: (path, from_line, to_line)
```

Add methods:
- `get_or_create_arc(key: tuple[str, int, int]) -> ArcData`
- `arcs_by_file() -> dict[str, dict[tuple[int, int], ArcData]]`

Keep the existing `LineData` and line-level tracking unchanged — line
execution counts are still needed for statement coverage, assert distribution,
test attribution, and the HTML/CSV/JSON reporters.

### Phase 2: Use observed arcs for branch analysis

**Goal:** Replace heuristic branch detection with direct arc lookups.

**Changes to report_data.py `_analyze_branches()`:**

The static_arcs path becomes:

```python
if file_analysis.static_arcs is not None:
    arcs_total = len(file_analysis.static_arcs)
    observed_arcs = store.arcs_for_file(path)  # dict[(from, to), ArcData]

    arcs_covered = 0
    arcs_deliberate = 0
    arcs_incidental = 0
    partial = set()

    for (src, tgt) in file_analysis.static_arcs:
        arc_data = observed_arcs.get((src, tgt))
        if arc_data is not None and (arc_data.incidental_executions + arc_data.deliberate_executions) > 0:
            arcs_covered += 1
            if arc_data.deliberate_executions > 0:
                arcs_deliberate += 1
            if arc_data.incidental_executions > 0:
                arcs_incidental += 1

    # Partial detection: lines in static_arcs where some arcs taken, others not
    from collections import defaultdict
    arcs_by_source = defaultdict(list)
    for (src, tgt) in file_analysis.static_arcs:
        ad = observed_arcs.get((src, tgt))
        taken = ad is not None and (ad.incidental_executions + ad.deliberate_executions) > 0
        arcs_by_source[src].append(taken)
    for src, taken_list in arcs_by_source.items():
        if any(taken_list) and not all(taken_list):
            partial.add(src)
```

This completely eliminates BranchWalker from the static_arcs path. No more
heuristics, no more target-line matching, no more exit-scope workarounds.

**The fallback path** (no coverage.py) still needs BranchWalker for the
denominator (which branches exist). But the numerator can use observed arcs
to determine which were taken, falling back to heuristics only when arc data
is unavailable.

### Phase 3: Statement consolidation

**Goal:** Fix the multi-line statement tracing gap.

When computing statement coverage, map each executed line to its statement's
start line. If any line within a multi-line statement was executed, the
statement is covered.

This can use the AST: for each statement node, its `lineno` is the start
line, and its `end_lineno` is the end. If any line in `[lineno, end_lineno]`
has execution data, the statement is covered.

**Changes to report_data.py `build()`:**

In the statement counting loop (around line 74), when checking if a line is
covered, also check if any line in the same statement's span was executed.
The executable_lines analyzer already parses the AST, so the statement spans
are available.

### Phase 4: Clean up

**What becomes obsolete:**
- `BranchWalker.walk_branches()` true_taken/false_taken heuristics — no
  longer needed when arc data is available. The walker is still needed for
  the fallback path and for the HTML reporter's partial-branch coloring.
- The `false_target` matching logic in `_analyze_branches()` — replaced by
  direct arc lookup.
- The exit-scope workarounds we added in this session.

**What stays:**
- `BranchWalker` — still needed for the no-coverage.py fallback path and
  for HTML report annotations (partial branch coloring needs to know which
  specific arcs were missed, not just "some arc was missed").
- `BranchDescriptor` — still useful for deliberate/incidental per-branch
  reporting in HTML.
- `LineData` and all line-level tracking — statement coverage, assert
  distribution, test IDs, and all existing reporters depend on this.
- `static_arcs` computation in `executable_lines.py` — still provides the
  branch denominator (which arcs *should* exist).

## Key Design Decisions

### 1. Arc storage: separate dict vs extending LineData

**Recommendation: separate dict.** Arcs are keyed by `(path, from_line, to_line)`,
which is a different key space from lines `(path, lineno)`. Mixing them in
one dict would require a union key type and complicate all existing consumers.

### 2. Negative arcs: model exit-scope or not?

coverage.py uses negative target lines like `(153, -152)` to represent "exit
the scope defined at line 152." The tracer naturally sees "return" events,
which we can model as `(last_line_in_frame, -function_start_line)`.

**Recommendation: yes, record negative arcs.** This makes direct lookup
against `static_arcs` trivial. Without negative arcs, we'd need special-case
logic for every exit-scope arc.

For LineTracer: the "return" event in `_make_local_trace` provides the frame,
from which we can get `f_code.co_firstlineno` (function start line). Record
`(prev_line, -co_firstlineno)`.

For MonitoringLineTracer: register for `RETURN` events in addition to `LINE`.

### 3. Overhead considerations

The current tracer does one dict lookup per line event (`store.get_or_create`).
Arc recording adds a second dict lookup per line event (`store.get_or_create_arc`).
This roughly doubles the per-line-event overhead.

Mitigations:
- Use `defaultdict` for the arc store (same as the line store) — one lookup,
  no branching on hit vs miss.
- The `prev_line` tracking is just a local variable assignment — negligible.
- If overhead is a concern, arc recording could be opt-in (enabled only when
  branch coverage is requested). But branch coverage is always computed in
  the current implementation, so this would be a behavioral change.

### 4. Serialization

`SessionStore.to_dict()` / `from_dict()` need to be extended for arc data.
The JSON format should include an `arcs` section alongside the existing
line data. Backward compatibility: old JSON files without `arcs` should
still load (arcs default to empty).

### 5. xdist support

`SessionStore.merge()` needs to merge arc data from worker stores. Same
pattern as line data: add-assign execution counts.

## Test Strategy

1. **Unit tests for arc recording:** Write tracer-level tests that execute
   known code patterns and verify the correct arcs are recorded. Test:
   - Simple if/else
   - For loop (entry, body, exit)
   - Nested loops
   - Try/except
   - Comprehensions
   - Multi-line statements
   - Function return (negative arc)

2. **Unit tests for arc-based branch analysis:** Test `_analyze_branches`
   with mock arc data and verify it produces the same `_BranchAnalysis`
   as coverage.py for known patterns.

3. **Integration test:** Run the httpx comparison (compare_coverage.py) and
   verify convergence. The remaining divergences should be limited to:
   - Tracer conflict in combined runs (Python < 3.12 only)
   - Any constructs where the tracer genuinely can't observe arcs

4. **Regression:** All existing tests must pass. The line-level data model
   is unchanged, so existing reporter tests should be unaffected.

## Risks

1. **Performance:** Doubling dict lookups in the hot path may slow down
   large test suites. Benchmark before/after on httpx.

2. **Return event reliability:** On Python < 3.12, `sys.settrace` fires
   "return" events for normal returns but behavior for exceptions may vary.
   Test thoroughly with try/except code paths.

3. **MonitoringLineTracer prev_line tracking:** Without per-frame state,
   tracking prev_line requires a dict keyed by something stable (code object
   ID or thread+frame). This needs careful design to avoid memory leaks.

