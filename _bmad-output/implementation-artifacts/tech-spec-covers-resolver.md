---
title: '@covers Decorator & Resolver'
type: 'feature'
created: '2026-03-15'
status: 'done'
baseline_commit: '773d876bb2e59593bbf850a274bdc04b7632233d'
context:
  - _bmad-output/planning-artifacts/architecture.md
---

# @covers Decorator & Resolver

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The `@covers` decorator stores raw refs but nothing resolves them — the profiler cannot know which lines are deliberate, so no deliberate coverage is ever recorded.

**Approach:** Implement `resolve_covers(item)` in `covers.py`: converts each ref in `item.function._covers_refs` (or `item.cls._covers_refs` for class-level decoration) to a `frozenset[tuple[str, int]]` of absolute source lines, stores it on `item._covers_lines`. Update `covers()` to reject zero arguments. Add `plugin.py` hook stub wiring so the resolver is called at `pytest_runtest_setup`.

## Boundaries & Constraints

**Always:**
- `from __future__ import annotations` in every module
- Resolution is lazy for string specs — happens at `pytest_runtest_setup`. Evaluation is eager when real objects are used, like in `@covers(MyClass.my_method)` - where imports have already been done before the tests run
- Dotted strings: resolved via iterative `importlib.import_module` + `getattr` chain (longest prefix first)
- Direct object refs: used as-is — no import needed
- Class targets: all lines in class body + all lines of methods via `inspect.getmembers(cls, predicate=inspect.isfunction)`
- Source lines obtained via `inspect.getsourcefile` + `inspect.getsourcelines`; file path stored as `str(pathlib.Path(src_file).resolve())` — absolute, normalised
- Resolution failure → `pytest.fail(f"coverage-stats: cannot resolve @covers target {repr(ref)} for test {item.nodeid} — {reason}")` — NOT `raise`
- stdlib + pytest only — no third-party imports
- `covers()` with zero args: raise `TypeError("@covers requires at least one argument")`
- Class-level decorator: check `item.cls._covers_refs` when `item.function` has no `_covers_refs`
- Test item with no `@covers` (neither function nor class): set `item._covers_lines = frozenset()` and return

**Ask First:**
- If `inspect.getsourcefile` returns `None` for a valid callable — ask before deciding how to handle

**Never:**
- Resolve string refs at decoration time
- `raise CoverageStatsResolutionError(...)` directly — always use `pytest.fail()`
- `os.path` — use `pathlib.Path`
- Touch `store.py`, `profiler.py` internals, or any reporter

## I/O & Edge-Case Matrix

| Scenario                       | Input                                 | Expected Output                                                    | Error Handling |
|--------------------------------|---------------------------------------|--------------------------------------------------------------------|----------------|
| Function ref (direct object)   | `@covers(my_func)`                    | frozenset of `(abs_path, lineno)` for every line in `my_func` body | — |
| Dotted string ref              | `@covers("pkg.mod.MyClass.method")`   | frozenset of lines in resolved method                              | `pytest.fail` if unresolvable |
| Multiple Dotted string ref     | `@covers("pkg.mod.MyClass.method", "pkg.mod.MyClass.method")` | frozenset of lines in resolved methods                             | `pytest.fail` if unresolvable |
| Class ref                      | `@covers(MyClass)`                    | frozenset of class body lines + all method lines                   | — |
| List of refs                   | `@covers(fn_a, fn_b)`                 | union of both line sets                                            | — |
| Class-level decoration         | `@covers(MyClass)` on test class      | same as above, applied to every test method in class               | — |
| No `@covers`                   | test without decorator                | `item._covers_lines = frozenset()`                                 | — |
| Bad dotted string              | `@covers("no.such.thing")`            | —                                                                  | `pytest.fail(...)` |
| Zero args                      | `@covers()`                           | —                                                                  | `TypeError` at decoration time |
| `getsourcefile` returns `None` | built-in / C extension                | —                                                                  | `pytest.fail(...)` |

</frozen-after-approval>

## Code Map

- `src/coverage_stats/covers.py` — add zero-arg guard to `covers()`; add `resolve_covers(item)` + private helpers `_resolve_ref`, `_resolve_dotted_string`, `_get_source_lines`
- `src/coverage_stats/plugin.py` — update `pytest_runtest_setup` stub: call `resolve_covers(item)` instead of `raise NotImplementedError`
- `tests/unit/test_covers.py` — unit tests for all resolution paths

## Tasks & Acceptance

**Execution:**
- [ ] `src/coverage_stats/covers.py` -- IMPLEMENT -- add zero-arg guard; add `resolve_covers(item)`, `_resolve_ref(ref, item)`, `_resolve_dotted_string(ref, item)`, `_get_source_lines(target, ref, item)` per spec
- [ ] `src/coverage_stats/plugin.py` -- UPDATE `pytest_runtest_setup` -- replace `raise NotImplementedError` with: `from coverage_stats.covers import resolve_covers; resolve_covers(item)`; keep `if not self._enabled: return` guard
- [ ] `tests/unit/test_covers.py` -- IMPLEMENT -- tests for: zero-arg TypeError, direct function ref, direct class ref (class expansion), dotted string resolving to function, dotted string resolving to class, list of mixed refs, no-decorator item (frozenset empty), bad dotted string triggers pytest.fail, built-in ref triggers pytest.fail

**Acceptance Criteria:**
- Given `@covers(some_function)` on a test, when `resolve_covers(item)` is called, then `item._covers_lines` is a `frozenset` containing `(abs_path, lineno)` tuples for every line in `some_function`
- Given `@covers("coverage_stats.store.SessionStore")` on a test, when resolved, then `item._covers_lines` contains lines from `SessionStore` class body and all its methods
- Given a test with no `@covers`, when resolved, then `item._covers_lines == frozenset()`
- Given `@covers("nonexistent.module.Fn")`, when resolved, then `pytest.fail` is called with message containing the ref repr and test nodeid
- Given `@covers()`, when the decorator is applied, then `TypeError` is raised immediately
- Given `pytest tests/unit/test_covers.py -v`, then all tests pass

## Design Notes

**Dotted string resolution (longest-prefix-first import):**
```python
def _resolve_dotted_string(ref: str, item) -> Any:
    parts = ref.split(".")
    for i in range(len(parts), 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:i]))
            obj = module
            for attr in parts[i:]:
                obj = getattr(obj, attr)
            return obj
        except ImportError:
            continue
        except AttributeError as exc:
            pytest.fail(f"coverage-stats: cannot resolve @covers target {repr(ref)} "
                        f"for test {item.nodeid} — {exc}")
    pytest.fail(f"coverage-stats: cannot resolve @covers target {repr(ref)} "
                f"for test {item.nodeid} — no importable module prefix found")
```

**Class expansion:** `inspect.getmembers(cls, predicate=inspect.isfunction)` yields methods defined directly in the class (not inherited). Include all lines of both the class body and each method.

## Verification

**Commands:**
- `.venv/bin/pytest tests/unit/test_covers.py -v` -- expected: all tests pass
- `.venv/bin/ruff check src/coverage_stats/covers.py src/coverage_stats/plugin.py` -- expected: exit 0
