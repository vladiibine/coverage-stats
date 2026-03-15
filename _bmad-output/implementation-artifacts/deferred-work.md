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

**Source:** Review finding from project-scaffold adversarial review
**File:** `src/coverage_stats/store.py`
**Issue:** `get_or_create(self, key)` has no type annotation on `key` or return type. Intent is `key: tuple[str, int]` → `LineData`.
**Recommended fix:** In the `SessionStore` implementation story, annotate as `def get_or_create(self, key: tuple[str, int]) -> LineData`.
