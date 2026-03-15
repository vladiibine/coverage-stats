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
