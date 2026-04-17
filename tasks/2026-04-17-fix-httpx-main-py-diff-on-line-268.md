# Fix: `for` loop inside `with` block incorrectly marked partial on Python 3.10+

## Problem

When running on Python 3.10+, coverage-stats marks `httpx/_main.py` line 268
(`for chunk in response.iter_bytes():`) as **partially covered**, while coverage.py
reports it as fully covered. The discrepancy does not occur on Python 3.9.

The same bug affects any `for` loop (or other looping statement) that is the last
statement inside a `with` block, when the iterator is fully exhausted during the
test run.

## Root cause

### Bytecode line-number table changed in Python 3.10

On Python 3.10, CPython changed how the cleanup bytecode after a `for` loop is
annotated when the loop lives inside a `with` block.

For this function (simplified to the relevant structure):

```python
def download_response(...):          # line 251
    with rich.progress.Progress(     # line 255
        ...
    ) as progress:
        ...
        for chunk in response.iter_bytes():   # line 268
            download.write(chunk)             # line 269
            progress.update(...)              # line 270
```

The key bytecode instructions after the loop body:

| Offset | Instruction | Python 3.9 effective line | Python 3.10 effective line |
|--------|-------------|--------------------------|---------------------------|
| 160 | `JUMP_ABSOLUTE 130` | 270 | 270 |
| 162 | `POP_BLOCK` | 270 (inherited, no annotation) | **268** (explicit annotation) |
| 164 | `LOAD_CONST None` | 270 (inherited) | **255** (explicit annotation — the `with` line) |
| … | `RETURN_VALUE` | 270 | 255 |

### Tracer arc sequence differs

**Python 3.9** — when the loop iterator is exhausted:
1. `JUMP_ABSOLUTE` (line 270) → `FOR_ITER` (line 268) → LINE event → `arc(270, 268)`
2. `FOR_ITER` exhausted → `POP_BLOCK` (effective line 270 in Python 3.9) → LINE event → `arc(268, 270)`
3. `with`-block cleanup at line 270 → `RETURN_VALUE` → RETURN event → `arc(270, -251)`

But because the tracer last visited line 268 (step 2's predecessor), the RETURN
event fires at line 270, recording `arc(270, -251)`. At no point does the observed
arc `(268, -251)` appear… except it does, because on Python 3.9 the cleanup code
stays at the same effective line as the `for` statement. Specifically:

When `FOR_ITER` (line 268) is exhausted, it jumps to `POP_BLOCK`. The `POP_BLOCK` in
Python 3.9 has effective line 270 (inherited from loop body). But crucially, the
**RETURN event fires with the last seen `f_lineno`**, which after the final
`JUMP_ABSOLUTE → FOR_ITER → exhausted` sequence ends up being 268. Verified by
direct per-frame tracer:

```
# Python 3.9 observed arcs from the `for` line (line 7 in the minitest):
[(7, 8), (7, 8), (7, -5)]   # (7, -5) == loop exits → function returns ✓
```

**Python 3.10** — when the loop iterator is exhausted:
1. `JUMP_ABSOLUTE` (line 270) → `FOR_ITER` (line 268) → LINE event → `arc(270, 268)`
2. `FOR_ITER` exhausted → `POP_BLOCK` at **L268** (no new LINE event, same line)
3. `LOAD_CONST` at **L255** → LINE event → `arc(268, 255)`
4. `with`-block cleanup at line 255 → `RETURN_VALUE` → RETURN event → `arc(255, -251)`

```
# Python 3.10 observed arcs from the `for` line:
[(7, 8), (7, 8), (7, 6)]    # (7, 6) == loop exits → back to `with` line; (7, -5) NEVER seen
```

The static arc for "loop iterator exhausted" is `(268, -251)`. In Python 3.10,
coverage-stats never observes this arc — it observes `(268, 255)` instead, which
does not match any static arc from line 268. So line 268 is marked partial.

### Why coverage.py handles it correctly

Coverage.py has known about this CPython change since Python 3.10 beta:

```python
# coverage/env.py (7.10.7)
exit_through_with = (PYVERSION >= (3, 10, 0, "beta"))
```

It applies `fix_with_jumps()` inside `PythonParser.translate_arcs()`:

```python
def translate_arcs(self, arcs):
    return {(self.first_line(a), self.first_line(b)) for (a, b) in self.fix_with_jumps(arcs)}
```

`fix_with_jumps` detects arcs of the form `(inner_stmt_line, with_stmt_line)` and
translates them to `(inner_stmt_line, after_with_line_or_exit)`, matching the static
arc produced by `PythonParser.arcs()`. On Python 3.9, `exit_through_with` is False
so `fix_with_jumps` is a no-op.

Verified: calling `parser.translate_arcs(raw_310_arcs)` converts `(7, 6)` → `(7, -5)`:

```
# Python 3.10 / coverage 7.13.5
Raw observed:        [(7, 6), (7, 8), ...]
After translate_arcs: [(7, -5), (7, 8), ...]   # ✓ matches static arcs
```

On Python 3.9 / coverage 7.10.7, `translate_arcs` is a no-op for the arcs that
are already correct.

## Current workaround in coverage-stats (incomplete)

`src/coverage_stats/reporters/report_data.py` normalises observed arc targets
through `multiline_map` (the `_multiline`/`multiline_map` attribute on
`PythonParser`). This fixes a separate issue — multi-line expression arc
normalisation — but does **not** fix the `exit_through_with` issue, because:

- `multiline_map` maps physical lines within a multi-line statement to the
  statement's first line.
- The with-line jump (`268 → 255`) is not a multiline-statement issue; it is a
  control-flow arc that `fix_with_jumps` must handle.

## Proposed fix

Replace the bespoke `multiline_map` normalisation in
`_analyze_branches_from_arcs` with a call to `PythonParser.translate_arcs()`.
This is coverage.py's public, stable API for exactly this problem. It handles:

1. **`fix_with_jumps`** — the `exit_through_with` behaviour (the new issue).
2. **`first_line()` normalisation** — multiline statement normalisation (the old
   issue we solved with `multiline_map`).

Both fixes are version-gated inside coverage.py itself, so the behaviour on
Python 3.9 is unchanged.

### Changes needed

#### 1. `src/coverage_stats/executable_lines.py`

Store the `PythonParser` instance on `FileAnalysis` so that `translate_arcs` can
be called later during branch analysis:

```python
@dataclass
class FileAnalysis:
    ...
    # NEW: the PythonParser instance, available when coverage.py is installed.
    # Used to call translate_arcs() for version-specific arc normalisation.
    cov_parser: object | None = None   # coverage.PythonParser or None
```

In `ExecutableLinesAnalyzer.analyze()`, after calling `_parse_with_coverage`:

```python
return FileAnalysis(
    ...
    cov_parser=p,   # keep the parser alive
)
```

(The `p` local is already available at the call site of `_parse_with_coverage`.)

#### 2. `src/coverage_stats/reporters/report_data.py`

In `_analyze_branches`, pass `cov_parser` to `_analyze_branches_from_arcs` and
use `translate_arcs` to normalise observed arcs:

```python
def _analyze_branches_from_arcs(
    self,
    static_arcs: set[tuple[int, int]],
    observed_arcs: dict[tuple[int, int], ArcData],
    excluded: set[int],
    cov_parser=None,          # replaces multiline_map parameter
) -> _BranchAnalysis:

    # Normalise observed arcs through coverage.py's translate_arcs().
    # This handles both:
    #   - multi-line statement normalisation (first_line())
    #   - exit_through_with arc translation (fix_with_jumps(), Python 3.10+)
    if cov_parser is not None and hasattr(cov_parser, 'translate_arcs'):
        translated_keys = cov_parser.translate_arcs(observed_arcs.keys())
        # Build a lookup from translated arc → original ArcData.
        # When multiple raw arcs translate to the same key, merge by keeping any.
        lookup: dict[tuple[int, int], ArcData] = {}
        for raw_arc, arc_data in observed_arcs.items():
            translated = next(
                iter(cov_parser.translate_arcs([raw_arc])), raw_arc
            )
            if translated not in lookup:
                lookup[translated] = arc_data
    else:
        lookup = observed_arcs

    for src, tgt in static_arcs:
        arc_data = lookup.get((src, tgt))
        taken = arc_data is not None and (
            arc_data.incidental_executions + arc_data.deliberate_executions
        ) > 0
        ...
```

> **Note on efficiency**: `translate_arcs` accepts an iterable and returns a set,
> so calling it once on all keys is efficient. The mapping from translated arc back
> to the original `ArcData` can be built in one pass.

The `multiline_map` field on `FileAnalysis` and the `multiline_map` parameter on
`_analyze_branches_from_arcs` become **redundant** once this change is in place and
should be removed.

#### 3. Tests

The existing test `test_multiline_ternary_false_branch_not_partial` (currently
skipped on coverage ≥ 7.13.5 because `_multiline` was renamed to `multiline_map`)
should be **unskipped and generalised** to work with both coverage versions, since
the `translate_arcs` approach handles both old and new coverage.

A new test should be added for the `exit_through_with` case:

```python
@covers(DefaultReportBuilder._analyze_branches)
@pytest.mark.skipif(sys.version_info < (3, 10), reason="exit_through_with is Python 3.10+")
@pytest.mark.skipif(not _coverage_installed, reason="coverage.py not installed")
def test_for_in_with_loop_exit_not_partial(tmp_path):
    """for loop inside a with block: iterator exhaustion arc must not mark the for line partial.

    On Python 3.10+, the tracer records arc(for_line, with_line) when the
    iterator is exhausted (exit_through_with behaviour).  translate_arcs()
    must convert this to arc(for_line, -scope_first_line) so that the static
    arc (for_line, -scope_first_line) is seen as covered.
    """
    path = _write(tmp_path, """\
        class CM:
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def f(items):
            with CM():
                for x in items:
                    pass
    """)
    src = (tmp_path / "subject.py").read_text().splitlines()
    for_line  = next(i + 1 for i, ln in enumerate(src) if "for x" in ln)
    with_line = next(i + 1 for i, ln in enumerate(src) if "with CM" in ln)
    body_line = for_line + 1

    # Python 3.10+ tracer records arc(for_line, with_line) when loop exits.
    store = SessionStore()
    for ln in (for_line, body_line):
        ld = store.get_or_create((path, ln))
        ld.incidental_executions = 2
    store.get_or_create_arc((path, for_line, body_line)).incidental_executions = 2
    store.get_or_create_arc((path, body_line, for_line)).incidental_executions = 2
    # Simulate what Python 3.10 tracer records for loop exit:
    store.get_or_create_arc((path, for_line, with_line)).incidental_executions = 1

    fa = _analyzer.analyze(path)
    assert fa is not None and fa.static_arcs is not None

    line_data = {for_line: _ld(3), body_line: _ld(2)}
    result = DefaultReportBuilder()._analyze_branches(
        fa, line_data, store=store, abs_path=path
    )
    assert for_line not in result.partial, (
        f"Line {for_line} (for loop) should not be partial: "
        f"both branches taken — body entered and iterator exhausted via arc({for_line}, {with_line})"
    )
```

Follow red-green TDD: write the test first (it should fail without the fix), then
implement the fix in `_analyze_branches_from_arcs` and `executable_lines.py`.

## Files to change

| File | Change |
|------|--------|
| `src/coverage_stats/executable_lines.py` | Add `cov_parser` field to `FileAnalysis`; store parser in `analyze()` |
| `src/coverage_stats/reporters/report_data.py` | Replace `multiline_map` normalisation with `cov_parser.translate_arcs()` in `_analyze_branches_from_arcs`; update `_analyze_branches` call site |
| `tests/unit/test_reporters/test_partial_branches.py` | Add `test_for_in_with_loop_exit_not_partial`; un-skip and fix `test_multiline_ternary_false_branch_not_partial` |

## Verification

After implementing, run the full nox suite and confirm:
- `nox -s tests-3-9`: no regressions (Python 3.9 results unchanged)
- `nox -s tests-3-10`: new test passes, no other failures
- `nox -s tests-3-12`: new test passes (same code path as 3.10)
- `nox -s mypy lint`: clean

Also re-run `compare_cov_cs.py` against httpx with the Python 3.10 venv and
confirm `httpx/_main.py` line 268 no longer differs between the two tools.
