# `sys.settrace` fires `"return"` for generator yields, not just real returns (Python < 3.12)

On Python < 3.12, `sys.settrace` fires a `"return"` event every time a generator or async generator **suspends** at a `yield`, not only when it actually returns. If you record an exit arc `(last_line, -co_firstlineno)` on every `"return"` event, you get false arcs for each yield — arcs that coverage.py's C tracer never records.

**Detection**: inspect `frame.f_code.co_code[frame.f_lasti]`:
- `RETURN_VALUE` → real return
- `YIELD_VALUE` → yield, skip
- `YIELD_FROM` two bytes later → `yield from` delegation, skip
- `RESUME` (Python 3.11+) → generator resume point, skip (real return lands on any other opcode)

**On Python 3.12+** this is a non-issue: `sys.monitoring` has separate `PY_RETURN` and `PY_YIELD` events.

Fix lives in `src/coverage_stats/profiler.py` (`_is_real_return`). Test: `tests/integration/test_coverage_py_interop.py::test_generator_yields_do_not_create_false_exit_arcs`.
