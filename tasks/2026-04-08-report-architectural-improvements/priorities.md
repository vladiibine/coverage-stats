
## 7. Priority Matrix

| Improvement | Effort | Impact | Priority | Status      |
|---|---|---|---|-------------|
| 2.1 Reduce hot-path attribute lookups | Low | High (perf) | **P0** | done        |
| 2.2 `__slots__` on `LineData` | Low | Medium (perf + memory) | **P0** | done        |
| 5.2 Move `covers_lines` to `ProfilerContext` | Low | Medium (perf + clarity) | **P0** | done        |
| 2.3 `defaultdict` for `SessionStore` | Low | Low-Medium (perf) | **P1** | done        |
| 2.5 Precompute `_in_scope` prefixes | Low | Low (perf) | **P1** | done        |
| 1.3 Remove `assert_counter.py` | Low | Low (simplicity) | **P1** | done        |
| 1.4 Single-pass `FolderNode` aggregation | Low | Medium (perf for large codebases) | **P1** | done        |
| 1.2 Break up `report_data.py` | Medium | High (maintainability) | **P1** | done        |
| 5.1 Public iteration API on `SessionStore` | Low | Medium (encapsulation) | **P2** | done        |
| 1.1 Split `plugin.py` | Medium-High | High (maintainability + testability) | **P2** | done        |
| 2.4 Cache parsed ASTs | Medium | Medium (perf for reporting phase) | **P2** | not started |
| 3.2 Deduplicate branch walking | Medium | Medium (maintainability) | **P2** | not started |
| 4.1 Coverage.py version guarding | Low | Medium (robustness) | **P2** | done        |
| 3.1 Pluggable branch analyzer | Medium | Medium (extensibility) | **P3** | not started |
| 4.2 Tracer displacement detection | Low | Low (diagnostics) | **P3** | not started |
| 4.3 Tool ID fallback warnings | Low | Low (correctness) | **P3** | not started |
| 6.1 Unit tests for plugin | Medium | Medium (test coverage) | **P3** | not started |
| 6.2 Performance benchmarks | Medium | Medium (regression prevention) | **P3** | not started |
| 3.3 Event-based lifecycle | High | Low (premature unless needed) | **P4** | not started |
| 4.4 Thread safety docs | Low | Low (documentation) | **P4** | not started |
