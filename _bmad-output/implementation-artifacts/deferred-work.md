# Deferred Work

Items surfaced during review but not caused by the current story. Address in the relevant implementation story.

---

## `covers()` zero-argument validation

**Status:** RESOLVED in covers-resolver story. `covers()` raises `TypeError("@covers requires at least one argument")`.

---

## `SessionStore.get_or_create` type annotation

**Status:** RESOLVED in data-foundation story. Annotated as `def get_or_create(self, key: tuple[str, int]) -> LineData`.

---

## `SessionStore.from_dict` defensive validation

**Source:** Review findings from data-foundation adversarial review
**File:** `src/coverage_stats/store.py`
**Issue:** `from_dict` has no validation: missing null-byte in key raises `ValueError`; values list shorter than 4 raises `IndexError`; non-integer values corrupt silently.
**Context:** Internal xdist format — `to_dict` is the only producer. No real-world risk in MVP. Add validation if `from_dict` is ever exposed as a public API or deserializes untrusted data.

---

## `SessionStore.merge` self-merge behaviour

**Source:** Review findings from data-foundation adversarial review
**File:** `src/coverage_stats/store.py`
**Issue:** `store.merge(store)` doubles all values — no guard, no documentation.
**Context:** Never occurs in the intended xdist flow (workers are separate processes). Acceptable in MVP. Document if `merge` is ever exposed publicly.

---

## `covers.py` resolver robustness

**Source:** Review findings from covers-resolver adversarial review
**Files:** `src/coverage_stats/covers.py`

Three deferred hardening items (not blocking for MVP):

1. **Non-`ImportError` exceptions from `importlib.import_module`** — `SyntaxError`, `SystemExit`, etc. during module import propagate uncaught instead of producing a `pytest.fail` message. Rare in practice.

2. **`OSError` from `inspect.getsourcelines`** — if the source file is unreadable at test time, the exception propagates instead of a clean `pytest.fail`. Very rare.

3. **Inherited methods in class expansion** — `inspect.getmembers(cls, predicate=inspect.isfunction)` includes methods inherited from parent classes, which inflates the covered line set for subclasses. Document this behaviour; revisit if users report unexpected coverage inflation.

4. **`NoReturn` type annotation** — `_get_source_lines` else branch calls `pytest.fail()` (which never returns) but is not annotated `-> NoReturn`. Causes mypy strict-mode warnings. Fix when mypy is added to CI.

---

## `LineTracer` previous trace chaining

**Source:** Review findings from profiler adversarial review
**File:** `src/coverage_stats/profiler.py`
**Issue:** `_trace` calls `self._prev_trace(frame, event, arg)` but ignores the return value. The previous tracer's local trace return value (e.g., a per-frame trace from pytest's own tracer) is discarded. This can cause the previous tracer to lose frame-level tracing.
**Context:** Affects coverage.py and pytest's assertion rewriting when composed. Acceptable for MVP single-plugin use. Fix when adding xdist or composability support.

---

## `LineTracer.start()` called twice

**Source:** Review findings from profiler adversarial review
**File:** `src/coverage_stats/profiler.py`
**Issue:** Calling `start()` twice overwrites `_prev_trace` with `self._trace` itself, creating a self-referential loop. `stop()` then restores `self._trace` instead of the original tracer.
**Context:** `start()` is called once in `pytest_configure` and never again in the intended flow. Acceptable for MVP. Add a guard if `LineTracer` is ever exposed publicly.

---

## `distribute_asserts` — `current_test_item` None guard

**Source:** Review findings from assert-counter adversarial review
**File:** `src/coverage_stats/assert_counter.py`
**Issue:** Inside the `if count and ctx.current_test_lines:` branch, `getattr(ctx.current_test_item, "_covers_lines", frozenset())` is called without an explicit None check. If `current_test_item` is None (abnormal call path), all asserts are silently misclassified as incidental rather than raising an error.
**Context:** Unreachable in the intended flow — `current_test_lines` is only populated during "call" phase, which requires `current_test_item` to be set. Safe for MVP. Add an explicit guard if `distribute_asserts` is ever called from a second call site.

---

## `ProfilerContext.current_test_lines` thread safety

**Source:** Review findings from assert-counter adversarial review
**File:** `src/coverage_stats/profiler.py`, `src/coverage_stats/assert_counter.py`
**Issue:** `current_test_lines` is a plain `set` written by `LineTracer._trace` and cleared by `distribute_asserts`. Not thread-safe under in-process parallelism (e.g., threaded test frameworks).
**Context:** `sys.settrace` is per-thread; standard pytest is single-threaded. Acceptable for MVP. Revisit if threaded worker support is added.

---

## Reporter output warning for unknown format tokens

**Source:** Review findings from json-csv-reporters adversarial review
**File:** `src/coverage_stats/plugin.py`
**Issue:** Format tokens other than `json`, `csv`, `html` are silently ignored. A user typo like `--coverage-stats-format=jsn` produces no output and no error.
**Context:** Acceptable for MVP. Add a `warnings.warn` for unrecognised tokens when user-facing error messages are polished.

---

## Reporter dispatch when `store` is `None`

**Source:** Review findings from json-csv-reporters adversarial review
**File:** `src/coverage_stats/plugin.py`
**Issue:** If `pytest_configure` sets `_enabled=True` but raises before assigning `plugin._store`, `pytest_sessionfinish` will pass `None` to reporters, causing `AttributeError` on `store._data`.
**Context:** Unreachable in the intended flow. Acceptable for MVP. Add a `if self._store is None: return` guard if `CoverageStatsPlugin` is ever subclassed or instantiated outside `pytest_configure`.

---

## HTML reporter — href URL-encoding

**Source:** Review findings from html-reporter adversarial review
**Files:** `src/coverage_stats/reporters/html.py`
**Issue:** `href` attributes in index.html link to per-file filenames using bare string interpolation. Filenames containing `#`, `?`, `&`, or spaces will produce broken hrefs.
**Context:** Affects edge-case filenames only. Use `urllib.parse.quote(file_html_name)` in the `href` when polishing user-facing output.

---

## HTML reporter — per-file filename collision

**Source:** Review findings from html-reporter adversarial review
**Files:** `src/coverage_stats/reporters/html.py`
**Issue:** Per-file HTML name is `rel_path.replace("/", "__") + ".html"`. Paths `a/b__c.py` and `a__b/c.py` both produce `a__b__c.py.html`, causing one file to overwrite the other silently.
**Context:** Rare in practice. Use a collision-resistant scheme (e.g., hash suffix) if this becomes a user-reported issue.

---

## HTML reporter — abs_path_map last-writer-wins for duplicate rel_path

**Source:** Review findings from html-reporter adversarial review
**Files:** `src/coverage_stats/reporters/html.py`
**Issue:** `_group_by_rel_path` builds `abs_path_map[rel_path] = abs_path` with no collision check. If two absolute paths map to the same relative path (e.g., symlinks), the last writer wins and source lines may be read from the wrong file.
**Context:** Only possible with symlinks or unusual VCS setups. Acceptable for MVP.

---

## HTML reporter — top-level files show `"."` as folder label

**Source:** Review findings from html-reporter adversarial review
**Files:** `src/coverage_stats/reporters/html.py`
**Issue:** `str(Path(rel_path).parent)` returns `"."` for top-level files (e.g., `conftest.py`), so the folder section header reads `"."` instead of something user-friendly like `"(root)"`.
**Context:** Cosmetic. Replace `"."` with `"(root)"` when polishing the HTML output.
