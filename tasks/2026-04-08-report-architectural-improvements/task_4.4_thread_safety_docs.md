# Task 4.4 — Thread safety documentation

**Priority:** P4
**Effort:** Low
**Impact:** Low (documentation)

## Problem

`SessionStore._data` is a plain `dict` and `ProfilerContext` fields (`current_test_lines`, `current_assert_count`, `current_phase`) are mutated without any synchronization. This is safe under the current assumptions (single-process, single-threaded test execution, or multi-process via xdist), but those assumptions are implicit and undocumented.

Users who run tests with `pytest-parallel` (thread-based parallelism), or whose tests themselves spawn threads that execute covered code, could see corrupted data:
- Concurrent `store.get_or_create()` calls racing on `_data`
- A second thread recording a line while `distribute_asserts` is iterating `current_test_lines`
- `current_assert_count` incremented from multiple threads

There is no warning or error — the data corruption is silent.

## Solution

**Immediate (documentation):** Add a comment to `SessionStore` and `ProfilerContext` documenting the threading assumptions:

```python
class SessionStore:
    """Maps (abs_path, lineno) → LineData for the current test session.

    Thread safety: NOT thread-safe. This class assumes single-threaded
    access within a process. xdist parallelism is safe because each
    worker runs in a separate process with its own store. Thread-based
    parallelism (e.g., pytest-parallel) is NOT supported.
    """

@dataclass
class ProfilerContext:
    """Per-session tracing state.

    Thread safety: NOT thread-safe. All fields assume single-threaded
    mutation from pytest hooks and the tracer callback. If tests spawn
    threads that execute covered code, line data from those threads
    will be recorded (via the tracer) but assert and test counts will
    be unreliable.
    """
```

**If thread safety becomes a requirement in the future:**

1. `SessionStore`: add a `threading.Lock` around `get_or_create` and `merge`
2. `ProfilerContext.current_test_lines`: switch to a thread-local set, one per thread
3. `ProfilerContext.current_assert_count`: switch to `threading.local()` or an atomic counter
4. Document which fields are intentionally shared (e.g., `source_dirs`) vs. per-thread

For now, documenting the assumption is the right level of investment — implementing locking adds overhead to the hot path for a use case that likely doesn't exist yet.
