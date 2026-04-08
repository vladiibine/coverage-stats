# Task 5.1 — Public iteration API on `SessionStore`

**Priority:** P2
**Effort:** Low
**Impact:** Medium (encapsulation)

## Problem

`SessionStore._data` is marked private (underscore prefix) but accessed directly by two external consumers:

- `DefaultReportBuilder.build()` (`report_data.py:236`): `for (abs_path, lineno), ld in store._data.items()`
- `CoveragePyInterop.full_arcs_for_store()` (`report_data.py:669`): `for (path, lineno), ld in store._data.items()`
- `_flush_pre_test_lines()` (`plugin.py:115`): `if key not in store._data`

The underscore convention signals "don't touch this from outside the class", but the entire reporting layer depends on direct dict access. This makes it impossible to change the internal storage format (e.g., switching to a more efficient structure) without touching consumers.

## Solution

Add public iteration and lookup methods to `SessionStore`:

```python
class SessionStore:
    def items(self) -> Iterator[tuple[tuple[str, int], LineData]]:
        """Iterate over all (path, lineno) → LineData entries."""
        return iter(self._data.items())

    def __contains__(self, key: tuple[str, int]) -> bool:
        return key in self._data

    def files(self) -> dict[str, dict[int, LineData]]:
        """Group line data by file path — convenience for report builders."""
        result: dict[str, dict[int, LineData]] = {}
        for (path, lineno), ld in self._data.items():
            result.setdefault(path, {})[lineno] = ld
        return result
```

Then update all call sites:
- `store._data.items()` → `store.items()`
- `key not in store._data` → `key not in store`
- Optionally use `store.files()` in `DefaultReportBuilder.build()` to simplify the grouping loop there.

This lets the internal dict be swapped out (e.g., for a `defaultdict`, a `__slots__` structure, or an on-disk store) without breaking consumers.
