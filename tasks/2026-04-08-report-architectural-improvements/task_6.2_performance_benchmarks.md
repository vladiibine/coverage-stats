# Task 6.2 — Performance benchmarks

**Priority:** P3
**Effort:** Medium
**Impact:** Medium (regression prevention)
**Status:** Done

## Problem

The TODO.md notes "check that performance is not seriously degraded" as done, but there are no persistent, reproducible benchmarks. This means:

- Performance regressions from hot-path changes (e.g., adding an attribute lookup to the tracer) are invisible until someone notices slow tests
- There is no baseline to compare against after implementing the P0 performance tasks (2.1, 2.2, 5.2)
- "Not seriously degraded" is subjective without a number

## Solution

Add a benchmark test suite under `tests/benchmarks/` using `pytest-benchmark` (or a simple `timeit`-based approach if avoiding the dependency is preferred):

### Tracer hot-path benchmark

```python
# tests/benchmarks/test_tracer_perf.py
def test_tracer_line_throughput(benchmark):
    """Measure how many line events/sec the tracer can process."""
    store = SessionStore()
    ctx = ProfilerContext(source_dirs=["/src"])
    ctx.current_phase = "call"
    ctx.current_test_item = mock_item_with_covers([])

    tracer = LineTracer(ctx, store)
    # Simulate a local trace function call
    local = tracer._make_local_trace("/src/example.py", None)

    frame = make_mock_frame("/src/example.py")

    def run():
        for i in range(10_000):
            local(frame, "line", None)

    result = benchmark(run)
    # Assert throughput is above a minimum threshold
    # (adjust after establishing baseline)
```

### Store throughput benchmark

```python
def test_store_get_or_create_throughput(benchmark):
    store = SessionStore()
    keys = [("/src/a.py", i) for i in range(1000)]

    def run():
        for key in keys:
            store.get_or_create(key)

    benchmark(run)
```

### Reporting phase benchmark

```python
def test_report_build_time(benchmark, large_store_fixture):
    """Measure time to build a CoverageReport for a ~500-file store."""
    builder = DefaultReportBuilder()
    config = mock_config(rootpath="/repo")

    benchmark(lambda: builder.build(large_store_fixture, config))
```

**Integration with CI:** Run benchmarks in a dedicated nox session (`nox -s benchmark`) rather than on every commit. Store results as artifacts and fail if throughput drops more than 20% from the last stored baseline.

**Immediate use:** Run the benchmark suite before and after implementing tasks 2.1, 2.2, and 5.2 to quantify their impact.
