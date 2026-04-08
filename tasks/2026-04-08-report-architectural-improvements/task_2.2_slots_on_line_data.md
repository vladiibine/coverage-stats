# Task 2.2 — Use `__slots__` on `LineData`

**Priority:** P0
**Effort:** Low
**Impact:** Medium (perf + memory)
**Status: Done**

## Problem

`LineData` is a regular dataclass, so every instance carries a `__dict__` (~200 bytes of overhead). For a 10k-line codebase with 30% coverage, that means ~3,000 `LineData` instances = ~600 KB of pure dict overhead. More critically, attribute access on `__dict__`-based objects is slower than slot-based access because Python must go through the instance dictionary.

The tracer increments `ld.deliberate_executions` or `ld.incidental_executions` on every single line event, so this attribute-access cost is paid millions of times per test run.

## Solution

Add `slots=True` to the dataclass decorator (Python 3.10+):

```python
@dataclass(slots=True)
class LineData:
    incidental_executions: int = 0
    deliberate_executions: int = 0
    incidental_asserts: int = 0
    deliberate_asserts: int = 0
    incidental_tests: int = 0
    deliberate_tests: int = 0
```

For Python 3.9 compatibility (the project's minimum), add `__slots__` manually:

```python
@dataclass
class LineData:
    __slots__ = (
        "incidental_executions", "deliberate_executions",
        "incidental_asserts", "deliberate_asserts",
        "incidental_tests", "deliberate_tests",
    )
    incidental_executions: int = 0
    deliberate_executions: int = 0
    incidental_asserts: int = 0
    deliberate_asserts: int = 0
    incidental_tests: int = 0
    deliberate_tests: int = 0
```

Note: manual `__slots__` on a dataclass with defaults requires Python 3.10+ for `slots=True`, but the manual approach works on 3.9. Verify there are no dynamic attribute additions to `LineData` instances anywhere in the codebase before making this change (a grep for `setattr.*LineData` or `ld\.` assignments to unknown fields should confirm).

**Expected gains:** ~40% memory reduction per instance, measurable improvement in attribute-access speed in the tracer hot path.
