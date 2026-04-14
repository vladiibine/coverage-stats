# Fix multi-line statement arc normalization

## Problem

When Python executes a multi-line statement like:

```python
if "timeout" not in extensions:
    timeout = (
        self.timeout
        if isinstance(timeout, UseClientDefault)
        else Timeout(timeout)
    )
```

The LINE event fires on an inner line (e.g. line 374) rather than the statement start (line 372). Our tracer records `(371, 374)` but coverage.py's `static_arcs` expects `(371, 372)`. This causes 27 of 36 missing arcs vs coverage.py on httpx.

This affects both multi-line targets (e.g. `(if_line, inner_body_line)` instead of `(if_line, stmt_start)`) and multi-line sources (e.g. `(inner_condition_line, target)` instead of `(elif_line, target)`).

## Solution

### When coverage.py is installed

Use `PythonParser.translate_arcs()` to normalize observed arcs before matching against `static_arcs`. This method uses `PythonParser._multiline` — a dict mapping every physical line of a multi-line statement to its canonical first line — to normalize both ends of each arc pair.

Verified behavior:
- `translate_arcs({(4, 7)})` → `{(4, 5)}` when lines 5-9 form one statement
- `translate_arcs({(5, 8)})` → `{(5, 7)}` for multi-line elif conditions
- `translate_arcs({(8, 12)})` → `{(7, 7)}` normalizing both source and target

### When coverage.py is not installed

Build a `_multiline`-equivalent dict from the AST: for each `ast.stmt` node spanning multiple lines (`end_lineno > lineno`), map every line in `range(lineno, end_lineno + 1)` to `lineno`. Use this to normalize arc endpoints the same way. This won't produce identical results to coverage.py (e.g. coverage.py's parser handles token-level spans more precisely) but will cover the common cases.

Note: `_build_stmt_spans` in `report_data.py` already computes similar data but keyed differently (start → list of lines). The fallback can reuse that logic, inverted to line → start.

## Implementation

### 1. Expose `_multiline` from `ExecutableLinesAnalyzer`

Add a `multiline_map: dict[int, int] | None` field to `FileAnalysis`. Populate it from `PythonParser._multiline` in `_parse_with_coverage`. For the non-coverage.py path, build it from AST stmt spans.

```python
# In FileAnalysis dataclass
multiline_map: dict[int, int] | None = None
```

```python
# In _parse_with_coverage, after p.parse_source()
multiline_map = dict(p._multiline)
```

```python
# Fallback (no coverage.py), build from AST
def _build_multiline_map(tree: ast.Module) -> dict[int, int]:
    result = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        if end is not None and end > start:
            for ln in range(start, end + 1):
                result.setdefault(ln, start)
    return result
```

### 2. Normalize observed arcs in `_analyze_branches_from_arcs`

Pass `multiline_map` into `_analyze_branches_from_arcs`. Before matching, normalize each observed arc's source and target through the map.

```python
def _normalize_arc(self, arc: tuple[int, int], multiline: dict[int, int]) -> tuple[int, int]:
    src, tgt = arc
    src = multiline.get(src, src)
    tgt = multiline.get(tgt, tgt) if tgt > 0 else tgt
    return (src, tgt)
```

Then in the matching loop, for each `(src, tgt)` in `static_arcs`, check both the raw and normalized observed arcs.

### 3. Thread `multiline_map` through

- `_analyze_branches` already receives `file_analysis` → extract `multiline_map` from it
- Pass it to `_analyze_branches_from_arcs` as a new kwarg
