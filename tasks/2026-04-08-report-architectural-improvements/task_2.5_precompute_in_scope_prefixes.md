# Task 2.5 — Precompute `_in_scope` prefixes

**Priority:** P1
**Effort:** Low
**Impact:** Low (perf)

## Problem

Both `LineTracer._in_scope` and `MonitoringLineTracer._in_scope` construct `d + "/"` inside the loop on every call:

```python
def _in_scope(self, filename: str) -> bool:
    if self._context.source_dirs:
        return any(
            filename == d or filename.startswith(d + "/")
            for d in self._context.source_dirs
        )
```

`_in_scope` is called once per unique `co_filename` (the scope cache means it won't be called per-line), but the string concatenation `d + "/"` still occurs on every call for every source dir. For a project with 5 source dirs, that's 5 string allocations per unique file.

While the scope cache (`_scope_cache`) caps the total number of calls, this is still unnecessary work that is trivially avoidable.

## Solution

Precompute the prefix tuples once in `__init__`:

```python
class LineTracer:
    def __init__(self, context: ProfilerContext, store: SessionStore) -> None:
        self._context = context
        self._store = store
        self._source_prefixes: list[tuple[str, str]] = [
            (d, d + "/") for d in context.source_dirs
        ]
        ...

    def _in_scope(self, filename: str) -> bool:
        if self._source_prefixes:
            return any(
                filename == d or filename.startswith(p)
                for d, p in self._source_prefixes
            )
        prefix = sys.prefix if sys.prefix.endswith("/") else sys.prefix + "/"
        return "site-packages" not in filename and not filename.startswith(prefix)
```

Apply the same change to `MonitoringLineTracer`.

**Note:** `source_dirs` is set at construction time and never mutated, so precomputing in `__init__` is safe. If `source_dirs` could change post-construction, use a property instead.
