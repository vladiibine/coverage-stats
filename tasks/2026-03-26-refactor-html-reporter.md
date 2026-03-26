# Refactor: Split HtmlReporter into focused classes

## Goals

1. Move CSS and JS static assets to proper `.css` and `.js` files.
2. Keep `HtmlReporter.write()` as the single public entry point — callers are unaffected.
3. Introduce `IndexPageReporter` and `FilePageReporter` as focused rendering classes.
4. `HtmlReporter` gains two factory methods — `get_index_reporter()` and `get_file_reporter()` — that return instances of these classes.
5. All configurable assets (CSS, JS, column metadata) remain as class attributes accessed via `self`, so subclassers can override them on any of the three classes.

---

## New file layout

```
src/coverage_stats/reporters/
    html.py                         # HtmlReporter (orchestrator) — unchanged public API
    html_report_helpers/
        __init__.py                 # empty
        mixins.py                   # HtmlReporterMixin (shared utilities)
        index_reporter.py           # IndexPageReporter
        file_reporter.py            # FilePageReporter
        style.css                   # extracted CSS (was _CSS string in html.py)
        script.js                   # extracted JS (was _JS string in html.py)
```

---

## Class designs

### `HtmlReporterMixin`  (`html/mixins.py`)

Holds the assets and utilities shared by both page types. Neither `IndexPageReporter` nor `FilePageReporter` should duplicate these.

**Class attributes:**
```python
CSS: str   # loaded from style.css at import time
JS: str    # loaded from script.js at import time
EXTRA_CSS: str = ""
EXTRA_JS: str = ""
```

**Methods moved here from `HtmlReporter`:**
- `_c(col, columns)` — static; builds `col-hidden` class attribute for `<th>` elements
- `_color_level(pct)` — static; maps percentage to colour level 0–9
- `_bucket_level(value, max_value)` — static; maps a ranged value to level 0–9
- `_col_controls_html(columns, labels, descs)` — renders the checkbox bar
- `_help_popup_html(popup_id, columns, labels, descs)` — renders the help modal

**Constructor:**
```python
def __init__(self, precision: int = 1) -> None:
    self.precision = precision
```

---

### `IndexPageReporter`  (`html_report_helpers/index_reporter.py`)

Responsible for everything related to the index page.

**Inherits from:** `HtmlReporterMixin`

**Class attributes (moved from `HtmlReporter`):**
```python
INDEX_COLUMNS: dict[str, bool]
INDEX_COL_LABELS: dict[str, str]
INDEX_COL_DESCS: dict[str, str]
```

**Methods moved here from `HtmlReporter`:**
- `_collect_ranges(node)` — DFS to find max values for range-bucketed columns
- `_collect_ranges_rec(node, maxv)` — recursive helper
- `_render_tree_rows(node, depth, parent_id, _ranges)` — emits folder/file rows
- `render_index_page(rows_html)` — assembles the full index HTML document, using `self.CSS`, `self.JS`, `self.EXTRA_CSS`, `self.EXTRA_JS`

---

### `FilePageReporter`  (`html_report_helpers/file_reporter.py`)

Responsible for everything related to individual file pages.

**Inherits from:** `HtmlReporterMixin`

**Class attributes (moved from `HtmlReporter`):**
```python
FILE_COLUMNS: dict[str, bool]
FILE_COL_LABELS: dict[str, str]
FILE_COL_DESCS: dict[str, str]
```

**Methods moved here from `HtmlReporter`:**
- `_collect_file_ranges(lines)` — finds max per-column values across all executable lines
- `_missed_ranges(missed)` — compact range string (e.g. `5-8, 12`)
- `render_file_stats(...)` — renders the summary stats bar
- `render_line(lineno, source_text, ld, executable, partial, _ranges)` — renders one source line
- `render_file_page(rel_path, stats_html, lines_html)` — assembles the full file HTML document
- `_write_file_page(file_report, out_path)` — coordinates the above and writes the file

---

### `HtmlReporter`  (`html.py`)

Becomes a thin orchestrator. Its own CSS/JS class attributes are kept for backward compatibility — existing subclasses that override `HtmlReporter.CSS` will still work if `get_index_reporter()` / `get_file_reporter()` are also overridden, or if we forward them (see migration note below).

**Class attributes retained:**
```python
CSS: str        # same default as HtmlReporterMixin.CSS (loaded from style.css)
JS: str         # same default as HtmlReporterMixin.JS (loaded from script.js)
EXTRA_CSS: str = ""
EXTRA_JS: str = ""
```

**New factory methods:**
```python
def get_index_reporter(self) -> IndexPageReporter:
    return IndexPageReporter(precision=self.precision)

def get_file_reporter(self) -> FilePageReporter:
    return FilePageReporter(precision=self.precision)
```

**`write()` is rewritten to delegate:**
```python
def write(self, report: CoverageReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    file_reporter = self.get_file_reporter()
    index_reporter = self.get_index_reporter()

    for fr in report.files:
        file_html_name = fr.summary.rel_path.replace("/", "__") + ".html"
        file_reporter._write_file_page(fr, output_dir / file_html_name)

    rows_html = "".join(index_reporter._render_tree_rows(report.root, depth=0, parent_id=""))
    (output_dir / "index.html").write_text(
        index_reporter.render_index_page(rows_html), encoding="utf-8"
    )
```

All other methods (`render_line`, `render_index_page`, `render_file_page`, etc.) are **removed from `HtmlReporter`**. The module-level shims at the bottom of `html.py` are updated to delegate to instances of the new classes directly.

---

## Loading CSS and JS from files

In `mixins.py`, load the assets at module import time using `importlib.resources` (Python ≥ 3.9):

```python
from importlib.resources import files as _res_files

def _load_asset(filename: str) -> str:
    return _res_files(__package__).joinpath(filename).read_text(encoding="utf-8")

class HtmlReporterMixin:
    CSS: str = _load_asset("style.css")
    JS: str = _load_asset("script.js")
    EXTRA_CSS: str = ""
    EXTRA_JS: str = ""
```

The `html_report_helpers/` package must be declared as a package data source in `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"coverage_stats.reporters.html_report_helpers" = ["*.css", "*.js"]
```

---

## Subclassing pattern after the refactor

To customise the index page only:
```python
class MyIndexReporter(IndexPageReporter):
    INDEX_COLUMNS = {**IndexPageReporter.INDEX_COLUMNS, "inc-asserts": True}
    EXTRA_CSS = "td { font-size: 0.8em; }"

class MyReporter(HtmlReporter):
    def get_index_reporter(self):
        return MyIndexReporter(precision=self.precision)
```

To replace the stylesheet entirely:
```python
class MyFileReporter(FilePageReporter):
    CSS = open("my_custom.css").read()

class MyReporter(HtmlReporter):
    def get_file_reporter(self):
        return MyFileReporter(precision=self.precision)
```

---

## Implementation steps

1. **Create `html_report_helpers/` package skeleton** — add the directory with an empty `__init__.py`.

2. **Extract CSS and JS to files** — copy the content of `_CSS` and `_JS` strings from `html.py` into `html_report_helpers/style.css` and `html_report_helpers/script.js`. Add the `package-data` entry to `pyproject.toml`.

3. **Implement `HtmlReporterMixin`** — load assets via `importlib.resources`; move `_c`, `_color_level`, `_bucket_level`, `_col_controls_html`, `_help_popup_html` into it.

4. **Implement `FilePageReporter`** — move `FILE_COLUMNS`, `FILE_COL_LABELS`, `FILE_COL_DESCS`, and all file-page methods from `HtmlReporter`. Verify all `self.CSS` / `self.JS` references resolve to class attributes.

5. **Implement `IndexPageReporter`** — move `INDEX_COLUMNS`, `INDEX_COL_LABELS`, `INDEX_COL_DESCS`, and all index-page methods from `HtmlReporter`.

6. **Rewrite `HtmlReporter`** — add `get_file_reporter()` and `get_index_reporter()`; rewrite `write()` to delegate; remove all methods now on sub-reporters; update module-level shims.

7. **Update imports across the codebase** — anything importing `render_line`, `render_index_page`, etc. from `html.py` continues to work via the shims (no change needed for callers). Internal test imports of private methods will need updating to the new module paths.

8. **Run the full test suite** — all 189 tests should pass without modification to test logic (only import paths in tests that reference moved private methods).

---

## What does NOT change

- `HtmlReporter.write(report, output_dir)` — same signature, same behaviour.
- The `--coverage-stats-reporter` plugin hook — still points at `HtmlReporter`.
- All public method names and signatures on `HtmlReporter`.
- Module-level shim functions in `html.py` (`write_html`, `render_line`, etc.).
