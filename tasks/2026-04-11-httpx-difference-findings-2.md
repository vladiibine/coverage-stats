# httpx Difference Findings – Round 2

**Date:** 2026-04-11  
**Goal:** Make coverage-stats statement + arc counts match coverage.py exactly, using the httpx library as the reference test case.

---

## Executive Summary

After fixing the `# pragma: no cover` implementation in the previous session, a systematic comparison against coverage.py's `PythonParser` revealed **six distinct categories** of differences between our AST-based line detection and coverage.py's bytecode-based approach. Three of these are caused by Python compiler optimizations that eliminate bytecode for certain statement types; one is a default exclusion pattern in coverage.py that we don't support; and one is a bug in our Pass 4 exclusion logic.

The `if TYPE_CHECKING:` discovery specifically came from the coverage.py documentation / default config: coverage.py ships with **three built-in `exclude_lines` patterns** (not just `# pragma: no cover`).

---

## Coverage.py's Three Default Exclusion Patterns

Coverage.py's default `exclude_list` (confirmed via `CoverageConfig().exclude_list`) contains:

```python
[
    '#\\s*(pragma|PRAGMA)[:\\s]?\\s*(no|NO)\\s*(cover|COVER)',   # pragma: no cover
    '^\\s*(((async )?def .*?)?\\)(\\s*->.*?)?:\\s*)?\\.\\.\\.\\s*(#|$)',  # ... stubs
    'if (typing\\.)?TYPE_CHECKING:',                              # TYPE_CHECKING blocks
]
```

We currently only implement the first pattern. The second and third are missing.

---

## Investigation Method

1. Ran `DefaultExclude` comparison: `PythonParser(text=src)` returns `None` from `parse_source()` — **it sets attributes in-place** (`p.statements`), not a return value. First attempts at comparison were broken because of this.

2. After fixing the API call, ran a full comparison across all `httpx/**/*.py` files:
   ```python
   p = PythonParser(text=src, exclude=DEFAULT_EXCLUDE)
   p.parse_source()
   cov_stmts = p.statements  # correct: attribute, not return value
   our_stmts = fa.executable_lines
   ```

3. Found 10 files with differences, grouped into 6 categories below.

---

## Category 1: `if TYPE_CHECKING:` Blocks

**Files affected:** `_api.py:22`, `_client.py:51`, `_config.py:10`, `_exceptions.py:39`, `_main.py:22`, `_transports/default.py:33`, `_transports/wsgi.py:12`

**What happens:** coverage.py's third default pattern `if (typing\.)?TYPE_CHECKING:` marks these lines for exclusion, and the entire if block is excluded. We count `if TYPE_CHECKING:` as an executable statement.

**Example (`httpx/_transports/wsgi.py`):**
```python
if typing.TYPE_CHECKING:   # line 12 — we count it; coverage.py excludes it + body
    from .._models import WSGIApp
```

**Fix needed:** Add `if (typing\.)?TYPE_CHECKING:` as a default exclusion pattern in `_excluded_lines`.

---

## Category 2: `while True:` / Constant-Condition While Loops

**Files affected:** `_auth.py:77,102`, `_client.py:941,970,1656,1685`

**What happens:** Python 3.9 optimizes `while True:` — the loop header line generates **no bytecode**. The bytecode jumps directly to the body. Coverage.py's tokenizer-based approach correctly omits this line; our AST walk adds it as `ast.While` (an `ast.stmt`).

**Confirmed via `dis`:**
```
while True:   # line 3 — NO bytecode here
    x = 1    # line 4 — LOAD_CONST / STORE_FAST
    break    # line 5 — JUMP_ABSOLUTE
```

**Fix needed:** In `_compute_executable_from_tree`, skip adding `ast.While.lineno` when the test is a truthy `ast.Constant` (e.g., `True`, `1`).

---

## Category 3: `global` and `nonlocal` Declarations

**Files affected:** `_transports/default.py:97` (`global HTTPCORE_EXC_MAP`), `_transports/asgi.py:135,149`, `_transports/wsgi.py:128` (`nonlocal` statements)

**What happens:** `global` and `nonlocal` are `ast.stmt` subclasses (so our walker adds them), but they generate **no bytecode** — they are purely compile-time declarations.

**Confirmed via `dis`:**
```python
def baz():
    global G      # line 4 — NO bytecode
    G = 1         # line 5 — LOAD_CONST / STORE_GLOBAL
```

**Fix needed:** Skip `ast.Global` and `ast.Nonlocal` nodes in `_compute_executable_from_tree`.

---

## Category 4: Annotation-Only Statements in Non-Class Scope

**Files affected:** `_multipart.py:125` (`fileobj: FileContent`)

**What happens:** An `ast.AnnAssign` with `value=None` (annotation without assignment) inside a function body generates **no bytecode** in Python 3.9. However, the same in a class body DOES generate bytecode (it updates `__annotations__`).

**Example:**
```python
def __init__(self, ...):
    fileobj: FileContent    # line 125 — no bytecode (we count it; cov.py doesn't)
    headers: dict = {}      # line 127 — has bytecode (both count it)
```

**Confirmed via `dis`:**
- Function body `x: int` → zero bytecode
- Class body `x: int` → `LOAD_NAME int`, `LOAD_NAME __annotations__`, `STORE_SUBSCR`

**Fix needed:** In `_compute_executable_from_tree`, skip `ast.AnnAssign` with `value=None` when the parent is not a `ast.ClassDef` (requires a parent-map traversal).

---

## Category 5: Constant Expression Statements

**Files affected:** `_config.py:15` (a `"""..."""` block the developer added as a note — not the first statement, so not a docstring)

**What happens:** Python 3.9 optimizes away ALL `ast.Expr` statements whose value is an `ast.Constant` — strings, numbers, `None`, `True`, `False`, `...` (Ellipsis). Our current `_docstring_lines` only removes the **first** string literal in each function/class/module body. Other constant expressions remain in our executable set.

**Confirmed via `dis`:**
```python
def foo():
    "docstring"    # no bytecode (stored in co_docstring, not LOAD_CONST)
    42             # no bytecode (optimized away)
    ...            # no bytecode (optimized away)
    "other str"    # no bytecode (optimized away)
    x = 1          # LOAD_CONST / STORE_FAST
```

**Fix needed:** Change `_docstring_lines` to exclude ALL `ast.Expr` with `ast.Constant` values (not just the first-in-body string). This is a simplification — the single rule "any `ast.Expr` with a constant value generates no bytecode" replaces the complex first-body-string detection.

---

## Category 6 (Bug): Pass 4 Over-Exclusion via `else:` / `finally:` Keywords

**Files affected:** `_transports/default.py` — lines 187–210 incorrectly excluded (an entire `elif` block)

**Root cause:** Pass 4 in `_excluded_lines` handles pragmas on "continuation lines" (e.g., `raise Foo(\n...\n)  # pragma: no cover` where the pragma is on the closing `)`). It computes:

```python
unmatched = pragma_lines - matched_linenos
```

`else:  # pragma: no cover` (line 211) has no AST node (it's a keyword, not a node). Pass 3 already handles it correctly (scans the gap between clauses). But `else:` still ends up in `unmatched` because it has no `lineno` in the AST. Pass 4 then finds the innermost spanning `ast.stmt` — the enclosing `elif` block at line 187 — and incorrectly excludes lines 187–210.

**Trace of the bug:**
```
pragma_lines = {190, 211, ...}       # line 190: except ImportError:, line 211: else:
After Pass 3: excluded += {211-215}  # else: block correctly excluded

# But:
matched_linenos = {190, ...}         # 211 has no AST node → unmatched
unmatched = {211}                    # should be empty after Pass 3 handled it!

# Pass 4 finds: ast.If at line 187 spans line 211
# → incorrectly excludes range(187, 211) = lines 187-210
```

**Fix needed:** Change Pass 4 to:
```python
unmatched = pragma_lines - matched_linenos - excluded  # skip already-handled lines
```

This prevents Pass 4 from re-processing pragma lines that Pass 3 (or Passes 1–2) already added to `excluded`.

---

## Summary Table

| # | Category | Files | Fix Location |
|---|----------|-------|-------------|
| 1 | `if TYPE_CHECKING:` not excluded | 7 files | `_excluded_lines`: add regex pattern |
| 2 | `while True:` line counted as executable | 2 files | `_compute_executable_from_tree` |
| 3 | `global`/`nonlocal` counted as executable | 3 files | `_compute_executable_from_tree` |
| 4 | Annotation-without-value in function counted | 1 file | `_compute_executable_from_tree` (needs parent map) |
| 5 | Non-docstring constant expressions counted | 1 file | `_docstring_lines` (generalize) |
| 6 | Pass 4 re-processes `else:` pragma → over-excludes | 1 file | `_excluded_lines` Pass 4 |

---

## What Already Works (After Round 1)

The previous session fixed all the `# pragma: no cover` issues. At that point, a comparison using `p.lines_matching(r'# pragma: no cover|# pragma: nocover', r'')` to pre-filter coverage.py's statements showed **ALL MATCH**. The remaining differences only appear when passing coverage.py's full default exclusion regex — including `if TYPE_CHECKING:` — to `PythonParser`.

---

## Open Question: Configurability

Coverage.py allows users to customize `exclude_lines` in `.coveragerc`/`pyproject.toml`. Our implementation currently has hard-coded string patterns. A future improvement would be to expose an `exclude_lines` setting in coverage-stats' pytest config, with the same three defaults as coverage.py. For now, hard-coding the defaults is sufficient to match coverage.py's out-of-the-box behavior.
