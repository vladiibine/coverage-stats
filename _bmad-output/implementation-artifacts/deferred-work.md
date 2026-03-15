# Deferred Work

Items surfaced during review but not caused by the current story. Address in the relevant implementation story.

---

## `covers()` zero-argument validation

**Source:** Review finding from project-scaffold adversarial review
**File:** `src/coverage_stats/covers.py`
**Issue:** `@covers()` with no arguments sets `_covers_refs = ()` — a silent no-op that produces no deliberate coverage records with no error. User gets incorrect statistics with no feedback.
**Recommended fix:** In the `covers` implementation story, add: `if not refs: raise TypeError("@covers requires at least one argument")`

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
