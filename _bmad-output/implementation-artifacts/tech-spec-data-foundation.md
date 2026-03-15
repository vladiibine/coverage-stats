---
title: 'Data Foundation — LineData & SessionStore'
type: 'feature'
created: '2026-03-15'
status: 'done'
baseline_commit: '0254d4d2607d519f0f0ca9e1fe364aeafa87e6ed'
context:
  - _bmad-output/planning-artifacts/architecture.md
---

# Data Foundation — LineData & SessionStore

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `LineData` and `SessionStore` are stubs — nothing can accumulate coverage data yet, blocking the profiler and all reporters.

**Approach:** Fully implement `LineData` (add zero defaults) and `SessionStore` (`get_or_create`, `merge`, `to_dict`, `from_dict`) in `store.py`, then unit-test all behaviours. `ProfilerContext` in `profiler.py` is already correct — no changes there.

## Boundaries & Constraints

**Always:**
- `from __future__ import annotations` at top of every module
- `pathlib.Path` for any path operations (none needed here — store deals in raw strings)
- `LineData` is a mutable `dataclass` — all four `int` fields default to `0`
- `SessionStore` key type: `tuple[str, int]` — `(abs_file_path, lineno)`
- `merge` is additive: for each key in `other`, sum all four fields into `self`
- `to_dict` / `from_dict` must round-trip losslessly through `json.dumps` / `json.loads` (xdist transport)
- Serialisation key format: `f"{abs_file_path}\x00{lineno}"` — null-byte separator; safe because file paths cannot contain null bytes
- stdlib only — no third-party imports
- `get_or_create` must annotate: `key: tuple[str, int]` → `LineData` (deferred-work item)

**Ask First:**
- If any architectural rule needs to be bent to satisfy a correctness requirement

**Never:**
- `__slots__` on `LineData` or `SessionStore` (MVP — correctness over micro-optimisation)
- Changing `ProfilerContext` in `profiler.py`
- Touching `LineTracer` stub in `profiler.py`
- Making `SessionStore` a dataclass (it has behavioural methods)

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `get_or_create` new key | key not in store | returns new `LineData(0,0,0,0)`, stored for next call | — |
| `get_or_create` existing key | key already in store | returns same object (identity, not copy) | — |
| `merge` additive | store A has `(f,1): (1,2,3,4)`, store B has `(f,1): (10,20,30,40)` | `(f,1)` becomes `(11,22,33,44)` | — |
| `merge` disjoint keys | A and B have no common keys | all keys from B added to A | — |
| `to_dict` → `from_dict` | arbitrary store | round-trip produces equal stores (same keys and field values) | — |
| `to_dict` empty store | store with no entries | returns `{}` | — |
| lineno with colon in path | path=`/a:b/c.py`, lineno=42 | null-byte separator prevents split ambiguity | — |

</frozen-after-approval>

## Code Map

- `src/coverage_stats/store.py` — `LineData` dataclass + `SessionStore` class (primary target)
- `src/coverage_stats/profiler.py` — `ProfilerContext` (read-only reference; do not modify)
- `tests/unit/test_store.py` — unit tests for all `SessionStore` behaviours

## Tasks & Acceptance

**Execution:**
- [ ] `src/coverage_stats/store.py` -- IMPLEMENT -- replace stubs with full implementation:
  - `LineData`: add `= 0` default to all four fields; keep as mutable dataclass
  - `SessionStore.__init__`: `self._data: dict[tuple[str, int], LineData] = {}`
  - `SessionStore.get_or_create(self, key: tuple[str, int]) -> LineData`: return existing or insert and return new `LineData(0, 0, 0, 0)`
  - `SessionStore.merge(self, other: SessionStore) -> None`: for each `(k, v)` in `other._data`: get_or_create(k), then add all four fields
  - `SessionStore.to_dict(self) -> dict`: return `{f"{path}\x00{lineno}": [ie, de, ia, da] for (path, lineno), ld in self._data.items()}`
  - `SessionStore.from_dict(cls, data: dict) -> SessionStore`: parse each key by splitting on `\x00` (rsplit limit=1 is not needed — lineno has no null bytes), reconstruct store
- [ ] `tests/unit/test_store.py` -- IMPLEMENT -- tests covering: `get_or_create` new/existing, `merge` additive/disjoint, `to_dict` empty/non-empty, `from_dict` round-trip, colon-in-path key safety

**Acceptance Criteria:**
- Given a new `SessionStore`, when `get_or_create(("f.py", 1))` is called twice, then both calls return the same `LineData` object
- Given two stores sharing key `("f.py", 5)` with values `(1,2,3,4)` and `(10,20,30,40)`, when `a.merge(b)`, then `a.get_or_create(("f.py", 5))` has fields `(11,22,33,44)`
- Given any populated store, when `SessionStore.from_dict(store.to_dict())` is called, then the result has identical keys and field values
- Given `src/coverage_stats/store.py`, when `ruff check src/coverage_stats/store.py` runs, then exit 0
- Given `tests/unit/test_store.py`, when `pytest tests/unit/test_store.py -v`, then all tests pass

## Design Notes

**`to_dict` / `from_dict` serialisation:**
```python
# to_dict
{f"{path}\x00{lineno}": [ld.incidental_executions, ld.deliberate_executions,
                          ld.incidental_asserts, ld.deliberate_asserts]
 for (path, lineno), ld in self._data.items()}

# from_dict — split on first null byte only
path, lineno_str = raw_key.split("\x00", 1)
key = (path, int(lineno_str))
```

## Verification

**Commands:**
- `pytest tests/unit/test_store.py -v` -- expected: all tests pass, exit 0
- `ruff check src/coverage_stats/store.py` -- expected: exit 0
