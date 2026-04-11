# Investigation: coverage-stats vs coverage.py discrepancies on httpx

**Date:** 2026-04-11  
**Test used:** `tests/test_config.py -k test_load_ssl_config_verify_existing_file`  
**Python:** 3.9.6  
**Tracer in use:** `LineTracer` (sys.settrace, Python < 3.12)

---

## The numbers

| Tool          | Covered lines in `httpx/_config.py` |
|---------------|--------------------------------------|
| coverage.py   | 51                                   |
| coverage-stats | 9                                   |

The 42 lines that coverage.py shows as covered but coverage-stats misses are **exclusively module-level code**: imports, `class`/`def` statements, and top-level assignments such as `DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)`. These lines all execute once, when the module is first imported, and never run again during a test call.

```
   1: from __future__ import annotations
   3: import os
   4: import typing
  26: class UnsetType:
  30: UNSET = UnsetType()
  33: def create_ssl_context(
  82: class Timeout:
 ...
 256: DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)
 257: DEFAULT_LIMITS = Limits(max_connections=100, max_keepalive_connections=20)
 258: DEFAULT_MAX_REDIRECTS = 20
```

All 9 lines that coverage-stats *does* capture are inside `SSLConfig.__init__` and `SSLConfig._load_ssl_context`, which execute during the test call itself.

---

## Root cause: tracer installation timing

### The key sequence on Python < 3.12 with pytest-cov

```
1. pytest_load_initial_conftests   [pytest-cov]
       → cov_controller.start() → CTracer installed as sys.settrace
       → conftest.py is now loaded here, with coverage.py's tracer ACTIVE

2. conftest.py loaded (tests/conftest.py line 20: import httpx)
       → httpx is fully imported: _config.py, _models.py, _urls.py, ...
       → ALL module-level code in httpx/_config.py runs
       → coverage.py captures every line ✓
       → coverage-stats tracer is NOT installed yet ✗

3. pytest_configure  [coverage-stats]
       → creates LineTracer, does NOT start it
         (comment: "deferred to pytest_sessionstart to avoid tracing
          heavyweight imports by other plugins during their configure hooks")

4. pytest_sessionstart  [coverage-stats, trylast=True]
       → tracer.start() called — now installed on top of coverage.py's CTracer
       → httpx._config is already in sys.modules
       → its module-level code will NEVER run again for this process

5. pytest_collectstart  [coverage-stats, trylast=True]
       → tracer reinstalled (coverage.py displaces us between steps 4 and 5)

6. test_config.py imported
       → import httpx → no-op, already in sys.modules
       → no line events for httpx/_config.py module-level code

7. pytest_runtest_call  [test running]
       → SSLConfig.__init__ etc. execute → captured as call-phase lines ✓
```

### Why coverage.py catches them and we don't

pytest-cov hooks into `pytest_load_initial_conftests`, which is designed to fire **before** conftest.py files are loaded. It starts coverage.py's C tracer there. Coverage.py is therefore active during the `import httpx` at conftest.py:20, and it records all of `httpx/_config.py`'s module-level execution.

Our tracer deliberately defers its `start()` to `pytest_sessionstart` to avoid capturing heavy plugin imports. By that point, httpx is already in `sys.modules` and will never be re-executed.

### Why sys.modules caching is irreversible

Python's import system is idempotent: once a module is in `sys.modules`, subsequent `import` statements are instant lookups with no code execution. There is no mechanism to trigger module-level code a second time without explicitly removing the entry from `sys.modules` (which would be unsafe and break running code).

---

## Scope of the problem

This affects **any module imported by conftest.py or by pytest plugins that load during startup**. For httpx, that's the entire `httpx` package, imported transitively via `tests/conftest.py:20`. In general, any project whose `conftest.py` imports the library under test will hit this — which is the common pattern.

For projects where the library is NOT imported from conftest.py (only from individual test files), our tracer IS active when the test module is first imported during `pytest_collectstart`, so module-level lines ARE captured correctly as pre-test lines.

---

## Secondary issue: coverage.py displacement on Python < 3.12

Even for modules imported after our tracer starts (i.e., test files themselves), coverage.py's C tracer can displace our sys.settrace tracer between collection phases. We partially handle this with `trylast=True` reinstalls in `pytest_collectstart` and `pytest_collection_finish`, but there are narrow windows where coverage.py is on top and we miss line events. This is a secondary contributor, smaller than the conftest import timing issue above.

---

## Potential fixes

### Option A: Start the tracer in `pytest_load_initial_conftests`

Move `tracer.start()` from `pytest_sessionstart` to a `pytest_load_initial_conftests` hook with `trylast=True`. This would put us on top of coverage.py's C tracer before conftest.py is loaded, so conftest-time imports would be traced.

**Pros:**
- Directly solves the root cause
- Same approach coverage.py takes

**Cons:**
- The deliberate deferral was to avoid tracing heavyweight plugin imports. With source-dir filtering now in place (`_source_prefixes`/`_exclude_prefixes`), the performance concern is much smaller — out-of-scope files are fast-rejected and their frames get `return None` immediately.
- `pytest_load_initial_conftests` receives `early_config`, not the full `config`. Need to verify `rootpath` and ini values are accessible.

### Option B: Retroactive attribution at `pytest_sessionstart`

At `pytest_sessionstart`, walk `sys.modules` and for any in-scope module that is already loaded, infer which top-level lines "must have run" by using the AST to find top-level executable statements (excluding function/class bodies) and attribute them as pre-test lines.

**Pros:**
- No timing change; avoids the `early_config` vs `config` complication

**Cons:**
- Inference rather than actual tracing — imprecise for modules whose top-level code calls functions or conditionally executes statements
- Does not capture lines inside functions called at module level (e.g. `UNSET = UnsetType()` would be found, but lines inside `UnsetType.__init__` would not)
- Adds complexity

### Option C: Accept and document the limitation

For projects like httpx where the library is imported from conftest.py, module-level lines are fundamentally unobservable by any tool that starts after conftest loading. Document this as a known limitation and suggest users set `coverage_stats_source` explicitly (so the source filter is tight and the report doesn't imply broader coverage than it shows).

---

## Recommendation

Option A is the right long-term fix. With the source-dir filter now always non-empty (rootdir fallback), the original performance concern is mitigated. The `early_config` accessibility needs a quick verification but is likely fine since `rootpath` and ini values are available there.

Option B could be a useful complement (for pre-test lines inside functions called at import time) but should not be the primary approach.
