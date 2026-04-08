# Splitting plugin.py: essential vs accidental complexity

## What is currently in plugin.py

The file contains four kinds of code:

| Kind | Examples |
|---|---|
| **Essential domain logic** | Flush pre-test lines, distribute asserts, merge worker stores, build + write reports |
| **Accidental: pytest wiring** | Hook methods, `trylast`/`tryfirst` decorators, `if not self._enabled: return` guards |
| **Accidental: xdist topology** | Worker vs controller role detection, JSON serialisation of the store, `pytest_testnodedown` merge |
| **Accidental: external-tool interop** | coverage.py `patch_coverage_save`, pyc-cache bypass, `sys.version_info < (3, 12)` branches |

`CoverageStatsPlugin` currently mixes all four. The guards (`if not self._enabled: return`) are the most visible symptom — every hook starts with one, because the same class handles both the inactive and active cases.

---

## Option A — thin-adapter split (`CoverageSession` + `CoverageStatsPlugin`)

**The idea.** Extract all state and domain behaviour into a `CoverageSession` object.  
`CoverageStatsPlugin` becomes a pure pytest adapter that owns no logic — it just calls `CoverageSession` at the right lifecycle moment.

```
CoverageSession
  start(source_dirs)
  stop()
  flush_pre_test_lines(ctx)
  on_test_setup(item)   # resolve @covers, reset ctx
  on_test_call(item)    # advance phase
  on_test_teardown(item, store)  # distribute asserts
  on_assertion_pass(item)
  merge_worker(raw_json)
  write_reports(config)

CoverageStatsPlugin   ← only pytest hooks; delegates entirely to CoverageSession
```

`pytest_configure` decides which role applies (worker / controller / single-process) and passes a correspondingly configured `CoverageSession` to the plugin. The `if not self._enabled` guard lives in one place only — at the start of each hook, calling `session.handle_X()` or returning early.

**Pros**
- `CoverageSession` can be unit-tested without `pytester` — just instantiate it and call its methods directly.
- The accidental complexity (hook ordering, `trylast`, role detection) is entirely confined to `CoverageStatsPlugin`.
- Adding a new lifecycle hook never touches domain code.

**Cons**
- `CoverageSession.write_reports(config)` still receives a `pytest.Config` — config parsing (`getoption`, `getini`) has to happen somewhere; it either leaks into `CoverageSession` or you parse config in `CoverageStatsPlugin` and pass primitives in.
- One more indirection layer for every hook call (minor).

---

## Option B — role-based split (`WorkerPlugin` + `ControllerPlugin`)

**The idea.** `pytest_configure` inspects the xdist role and registers a different plugin class depending on whether the process is a worker, controller, or single-process node.

```
_BasePlugin              (shared: enabled guard, store, customization)
  WorkerPlugin           (hooks: sessionstart, collectstart, collection_finish,
                          runtest_*, pytest_sessionfinish → serialise)
  ControllerPlugin       (hooks: pytest_testnodedown, pytest_sessionfinish → write reports)
  SingleProcessPlugin    (subclass of WorkerPlugin with reporting added,
                          or composes both)
```

Every `if _is_xdist_worker` / `if _is_xdist_controller` branch inside a hook disappears — each class only implements the hooks it needs.

**Pros**
- No conditional branching inside hooks at all; each class is responsible for exactly one role.
- `WorkerPlugin` and `ControllerPlugin` are individually much smaller and easier to reason about.

**Cons**
- `SingleProcessPlugin` needs both roles: either it inherits from both (multiple inheritance) or it composes them. Composition is cleaner but requires forwarding.
- Three test-plugin paths to cover instead of one.
- The xdist topology is still detected in `pytest_configure`, not eliminated.

---

## Option C — phase-based split (`TracingCoordinator` + `ReportingCoordinator`)

**The idea.** Split along the natural phase boundary: tracing (collection + execution) vs reporting (session finish + xdist merge). Both are registered as separate plugins and share the `SessionStore` via dependency injection.

```
TracingCoordinator      (owns: store, tracer, ctx)
  pytest_sessionstart
  pytest_collectstart
  pytest_collection_finish
  pytest_runtest_setup / call / teardown
  pytest_assertion_pass

ReportingCoordinator    (owns: store ref, customization)
  pytest_testnodedown   (xdist merge)
  pytest_sessionfinish  (write reports + coverage.py inject)
```

`pytest_configure` creates the store, hands it to both, and registers both.

**Pros**
- Clean single-responsibility separation: one class traces, one reports.
- Neither class is large.
- The pyc-cache hack, tracer reinstall dance, and `trylast` details stay isolated in `TracingCoordinator`.
- Coverage.py interop and xdist serialisation stay isolated in `ReportingCoordinator`.

**Cons**
- Two registered plugins; the inter-plugin shared state (the `SessionStore`) becomes explicit, which is good for testing but adds a visible seam.
- `pytest_sessionfinish` on a worker has to both flush pre-test lines (a tracing concern) and serialize (a reporting concern), so the phase boundary is slightly blurry at that one point.

---

## Option D — extract `XdistCoordinator` only (minimal change)

**The idea.** Keep `CoverageStatsPlugin` largely as-is but extract only the xdist-specific accidental complexity into a helper class.

```
XdistCoordinator
  serialise_worker(store, ctx, config)   → sets config.workeroutput
  merge_from_worker(node, store)         → replaces pytest_testnodedown body
  is_worker(config) / is_controller(config)
```

`CoverageStatsPlugin` delegates to it; the coverage.py injection on workers and the controller merge both live inside `XdistCoordinator`.

**Pros**
- Smallest diff; lowest risk.
- Targets the single messiest part of the file without a full restructuring.

**Cons**
- Does not address the essential/accidental separation holistically — `CoverageStatsPlugin` still mixes domain logic with pytest wiring for the single-process case.
- The `if not self._enabled` guard boilerplate stays.

---

## Recommendation

**Option C** is the strongest architectural move for this codebase at its current size:

- The tracing phase and reporting phase are genuinely independent concerns and the split along that line is natural.
- It makes `TracingCoordinator` and `ReportingCoordinator` independently testable without full integration tests.
- It doesn't require designing a new `CoverageSession` API or solving the "how do I avoid passing `pytest.Config` into domain code" problem that Option A raises.

**Option A** is the right long-term direction if you want to unit-test the domain logic (flush, merge, distribute-asserts) without `pytester` at all — but it requires deciding how config parsing is handled at the boundary, which is a separate design question.

**Option D** is the pragmatic first step if the goal is to clean up the file without committing to a larger restructuring.

A reasonable sequence: D → C → A (each can be done independently).
