# Task 2.3 — Use `defaultdict` for `SessionStore`

**Priority:** P1
**Effort:** Low
**Impact:** Low-Medium (perf)

## Problem

`SessionStore.get_or_create` is called on every line event — it is the hottest call site in the plugin after the tracer callback itself.

Current implementation:

```python
def get_or_create(self, key: tuple[str, int]) -> LineData:
    if key not in self._data:
        self._data[key] = LineData()
    return self._data[key]
```

On a cache miss this performs **two** dict lookups: one for `key not in self._data` and one for `self._data[key]`. On a cache hit (the common case for frequently-executed lines) it still does two lookups.

## Solution

Switch `_data` to a `defaultdict(LineData)`. This reduces every access to a single dict lookup regardless of whether the key exists:

```python
from collections import defaultdict

class SessionStore:
    def __init__(self) -> None:
        self._data: defaultdict[tuple[str, int], LineData] = defaultdict(LineData)

    def get_or_create(self, key: tuple[str, int]) -> LineData:
        return self._data[key]
```

`defaultdict` calls `LineData()` (the factory) only on a miss, so behavior is identical to the current implementation.

**Compatibility note:** `from_dict`, `to_dict`, `merge`, and `lines_by_file` all iterate `self._data.items()` — these work identically on `defaultdict`. The only subtle difference is that accessing a missing key now *creates* an entry, so code that checks `if key not in store._data` would silently create an empty `LineData`. A quick grep confirms this pattern only appears in `_flush_pre_test_lines` in `plugin.py` — that check should be updated to `if store._data[key].incidental_executions == 0 and store._data[key].deliberate_executions == 0` or restructured to avoid the negative lookup.
