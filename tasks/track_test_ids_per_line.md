# Task — Track test identifiers per executed line

**Effort:** Medium
**Impact:** High (new capability: per-line test attribution)
**Status:** Done

## Problem

`LineData` stores only aggregate counts (`incidental_tests: int`, `deliberate_tests: int`).
The actual test node IDs (e.g. `tests/test_billing.py::test_charge_refund[usd]`) are available
at recording time (`current_test_item.nodeid` in `ProfilerContext.distribute_asserts`) but are
discarded. Users cannot answer "which specific tests executed this line?" from the HTML report.

## Solution

Replace the two count fields with sets of node ID strings. Counts become `len(set)`, so all
existing derived metrics are preserved. Add an opt-in flag to keep the default behaviour
memory-efficient.

---

## Layer-by-layer changes

### 1. `src/coverage_stats/store.py` — `LineData`

Replace:
```python
incidental_tests: int = 0
deliberate_tests: int = 0
```
With:
```python
incidental_test_ids: set[str] = field(default_factory=set)
deliberate_test_ids: set[str] = field(default_factory=set)
```

The `_SLOTS_KW` workaround for Python 3.9 still works — `field(default_factory=set)` is valid
in both the slotted (3.10+) and non-slotted (3.9) forms.

Anywhere that previously read `.incidental_tests` / `.deliberate_tests` as a count now reads
`len(ld.incidental_test_ids)` / `len(ld.deliberate_test_ids)`.

### 2. `src/coverage_stats/store.py` — `SessionStore`

**`merge()`**: change `+=` to `|=` for the two ID fields.

**`to_dict()`**: the current format is a positional list of 6 ints. Extend to include the two
ID sets as JSON arrays at positions 4 and 5 (replacing the old int counts):
```
[inc_exec, del_exec, inc_assert, del_assert, [id, ...], [id, ...]]
```

**`from_dict()`**: add a backward-compat guard — if `values[4]` is a list, read it as a set of
strings; if it is an int (old format), fall back to an empty set (counts are lost but the store
remains valid):
```python
ld.incidental_test_ids = set(values[4]) if isinstance(values[4], list) else set()
ld.deliberate_test_ids = set(values[5]) if isinstance(values[5], list) else set()
```

### 3. `src/coverage_stats/profiler.py` — `ProfilerContext.distribute_asserts`

Two one-line changes (the only hot-path-adjacent code that changes; the actual per-line-event
tracer is untouched):
```python
# Before
ld.deliberate_tests += 1
ld.incidental_tests += 1

# After
ld.deliberate_test_ids.add(self.current_test_item.nodeid)
ld.incidental_test_ids.add(self.current_test_item.nodeid)
```

### 4. `src/coverage_stats/reporters/models.py` — `LineReport`

Replace:
```python
incidental_tests: int
deliberate_tests: int
```
With:
```python
incidental_test_ids: frozenset[str]
deliberate_test_ids: frozenset[str]
```

`FileSummary`, `IndexRowData`, and `FolderNode` do **not** aggregate test IDs up to the
file/folder level, so they are unchanged.

### 5. `src/coverage_stats/reporters/report_data.py` — `LineReport` construction

Mechanical change: copy frozensets instead of ints when building each `LineReport`.

### 6. `src/coverage_stats/reporters/html_report_helpers/file_reporter.py` — HTML display

The per-file page currently renders `incidental_tests` and `deliberate_tests` as plain numbers
in two data columns. With IDs available, the count cell can be made interactive:
- Keep the number as the visible cell content.
- Render the test node IDs as a hidden `<ul>` (or `data-*` attribute) that expands on click or
  hover via a small JS addition.
- Deliberate and incidental lists are rendered separately, preserving the existing distinction.

This is purely additive — the count display is unchanged for users who do not interact with it.

### 7. Opt-in flag (recommended)

Sets of strings are orders of magnitude heavier than two ints. For large CI suites (e.g. 10 000
covered lines × 200 tests touching each line × ~50-char node IDs ≈ 100 MB in memory, plus a
proportionally large xdist JSON payload) the always-on cost may be unacceptable.

Add a config option — e.g. `--coverage-stats-track-test-ids` / ini key
`coverage_stats_track_test_ids` — defaulting to `False`. When disabled, `LineData` keeps the
two int count fields and no IDs are stored, preserving the existing behaviour exactly. When
enabled, the set-based path is used.

The cleanest implementation: keep both field variants and select between them in
`distribute_asserts` based on a flag passed through `ProfilerContext`. Alternatively, use a
single code path with sets but only populate them when the flag is on.

---

## Files touched

| File | Nature of change |
|---|---|
| `src/coverage_stats/store.py` | `LineData` fields; `merge`, `to_dict`, `from_dict` |
| `src/coverage_stats/profiler.py` | `distribute_asserts` (2 lines) |
| `src/coverage_stats/tracing_coordinator.py` | Pass flag through to `ProfilerContext` if opt-in is implemented |
| `src/coverage_stats/plugin.py` | Register new CLI option / ini key |
| `src/coverage_stats/reporters/models.py` | `LineReport` fields |
| `src/coverage_stats/reporters/report_data.py` | `LineReport` construction |
| `src/coverage_stats/reporters/html_report_helpers/file_reporter.py` | Per-line test ID display |
| `src/coverage_stats/reporters/html_report_helpers/script.js` | Expand/collapse test list UI |
| `src/coverage_stats/reporters/html_report_helpers/style.css` | Styles for test list UI |
| `tests/unit/test_store.py` | Field renames, new merge/serialization behaviour |
| `tests/unit/test_profiler.py` | `distribute_asserts` assertions |
| `tests/unit/test_reporters/` | `LineReport` field renames throughout |

---

## Constraints

- The tracer hot path (`_make_local_trace` / `_monitoring_line`) must not change — test IDs are
  recorded once per test in `distribute_asserts`, not on every line event.
- The deliberate / incidental distinction must be preserved in the stored ID sets.
- Pre-test lines (module-level code executed before any test, tracked via `pre_test_lines`) have
  no associated test item. These lines should have empty ID sets (counts remain 0 or 1 depending
  on current behaviour — do not regress).
- xdist: the serialized format change must be backward-compatible in `from_dict` so a controller
  running a newer version can still merge data from an older worker (IDs are simply absent, counts
  fall back to 0).
- All functions must live on classes; methods must not call module-level free functions directly
  (consistent with the existing codebase constraint).
