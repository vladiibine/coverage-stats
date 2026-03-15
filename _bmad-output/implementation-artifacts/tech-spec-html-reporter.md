---
title: 'HTML Reporter'
type: 'feature'
created: '2026-03-15'
status: 'done'
baseline_commit: '5974520aee9f87fbda606109e3d259d80825562c'
context:
  - _bmad-output/planning-artifacts/architecture.md
---

# HTML Reporter

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `write_html` raises `NotImplementedError` and `html` format is silently skipped — users requesting an HTML report get no output.

**Approach:** Implement `write_html(store, config, output_dir)` with five helper functions, embedded CSS, and no CDN; wire `html` into `pytest_sessionfinish`.

## Boundaries & Constraints

**Always:**
- `from __future__ import annotations` in every module
- Signature: `write_html(store, config, output_dir: Path) -> None` — same `config` pattern as `write_json`/`write_csv`
- Relative path calculation: same `Path(abs_path).relative_to(Path(str(config.rootdir))).as_posix()` with `ValueError` fallback to absolute POSIX (identical to other reporters)
- All CSS/JS embedded inline; no external URLs, no CDN
- Folder collapsibility via HTML `<details>`/`<summary>` — no JavaScript required
- Per-file page filename: `rel_path.replace("/", "__") + ".html"` (e.g., `src/foo.py` → `src__foo.py.html`); written to `output_dir/`
- `index.html` written to `output_dir/index.html`
- `output_dir.mkdir(parents=True, exist_ok=True)` before writing any file
- Source lines: attempt `Path(abs_path).read_text(encoding="utf-8", errors="replace").splitlines()`; on any exception use `{}` (empty dict) so line numbers still render without source text
- Line colour in per-file page: deliberate (`deliberate_executions > 0`) → green; incidental only (`incidental_executions > 0`, no deliberate) → yellow; neither → no highlight
- Folder grouping: `str(Path(rel_path).parent)` — files in root map to folder `"."`
- Five helper functions from architecture (all return `str`):
  - `render_line(lineno, source_text, ld)` → `<tr>` row
  - `render_file_row(rel_path, lines, file_html_name)` → `<tr>` row in index
  - `render_folder_section(folder_name, file_rows_html)` → `<details>` block
  - `render_index_page(folder_sections_html)` → full `index.html` string
  - `render_file_page(rel_path, lines_html)` → full per-file page string
- CSS embedded as module-level `_CSS` string constant
- `plugin.py`: replace `elif fmt == "html": pass` with `write_html(self._store, config, output_dir)`
- stdlib + pytest only; no third-party imports

**Ask First:**
- If the per-file filename collision (two paths flatten to same name) needs resolution beyond MVP silent-overwrite

**Never:**
- CDN links or external resource URLs in any generated HTML
- `os.path` — use `pathlib.Path`
- Modify `store.py`, `json_reporter.py`, `csv_reporter.py`

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Empty store | `store._data == {}` | `index.html` written with no file rows; no per-file pages | — |
| Single file, two lines | one file in store | `index.html` + one `src__foo.py.html` written | — |
| Source file unreadable | `abs_path` does not exist | line rows render with lineno only; no crash | exception caught, source = `{}` |
| Path outside rootdir | abs_path not under rootdir | POSIX absolute path used as key; `ValueError` caught | — |
| Multiple files, multiple folders | two folders with two files each | `index.html` has two `<details>` sections | — |

</frozen-after-approval>

## Code Map

- `src/coverage_stats/reporters/html.py` — implement `write_html` + five helpers + `_CSS`
- `src/coverage_stats/plugin.py` — replace html skip with `write_html(self._store, config, output_dir)` call
- `tests/unit/test_reporters/test_html.py` — unit tests for helpers and `write_html` integration

## Tasks & Acceptance

**Execution:**
- [ ] `src/coverage_stats/reporters/html.py` -- IMPLEMENT -- add `_CSS` constant; implement `render_line`, `render_file_row`, `render_folder_section`, `render_index_page`, `render_file_page`; implement `write_html(store, config, output_dir)` that groups data by folder, builds pages, writes all files; update signature to accept `config`
- [ ] `src/coverage_stats/plugin.py` -- UPDATE -- replace `elif fmt == "html": pass` with `from coverage_stats.reporters.html import write_html; write_html(self._store, config, output_dir)`
- [ ] `tests/unit/test_reporters/test_html.py` -- CREATE -- tests: empty store writes index.html; single file writes index + per-file page; per-file page contains lineno; deliberate line gets green class; unreadable source falls back gracefully; index contains folder section; output dir created if missing

**Acceptance Criteria:**
- Given a populated store, when `write_html` runs, then `output_dir/index.html` exists and contains a `<details>` element per folder
- Given a file `src/foo.py` in the store, when `write_html` runs, then `output_dir/src__foo.py.html` exists
- Given a line with `deliberate_executions > 0`, when the per-file page is rendered, then the `<tr>` contains a green indicator
- Given an empty store, when `write_html` runs, then `index.html` is written with no errors
- Given `pytest tests/unit/test_reporters/test_html.py -v`, all tests pass

## Design Notes

**`write_html` skeleton:**
```python
def write_html(store, config, output_dir: Path) -> None:
    files = _group_by_rel_path(store, config)   # same defaultdict pattern as other reporters
    output_dir.mkdir(parents=True, exist_ok=True)
    folder_sections = []
    for folder, folder_files in sorted(_group_by_folder(files).items()):
        file_rows = []
        for rel_path, lines in sorted(folder_files.items()):
            file_html_name = rel_path.replace("/", "__") + ".html"
            _write_file_page(rel_path, lines, output_dir / file_html_name)
            file_rows.append(render_file_row(rel_path, lines, file_html_name))
        folder_sections.append(render_folder_section(folder, "".join(file_rows)))
    (output_dir / "index.html").write_text(
        render_index_page("".join(folder_sections)), encoding="utf-8"
    )
```

**Line colour logic in `render_line`:**
```python
if ld.deliberate_executions > 0:
    css_class = "deliberate"
elif ld.incidental_executions > 0:
    css_class = "incidental"
else:
    css_class = ""
```

## Verification

**Commands:**
- `.venv/bin/pytest tests/unit/test_reporters/test_html.py -v` -- expected: all tests pass
- `.venv/bin/ruff check src/coverage_stats/reporters/html.py src/coverage_stats/plugin.py` -- expected: exit 0
