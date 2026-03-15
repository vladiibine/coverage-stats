---
title: 'JSON & CSV Reporters'
type: 'feature'
created: '2026-03-15'
status: 'done'
baseline_commit: '4a9a42a34d4b2f6baf4c26f5f404ee6d9c69ce36'
context:
  - _bmad-output/planning-artifacts/architecture.md
---

# JSON & CSV Reporters

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The plugin collects coverage data but never writes any output — `pytest_sessionfinish` only stops the tracer, and both reporter stubs raise `NotImplementedError`.

**Approach:** Implement `write_json` and `write_csv` in their respective reporter modules; add `--coverage-stats-format` and `--coverage-stats-output` CLI/ini options; call the appropriate reporters from `pytest_sessionfinish`.

## Boundaries & Constraints

**Always:**
- `from __future__ import annotations` in every module
- Function signatures: `write_json(store, config, output_dir: Path) -> None` and `write_csv(store, config, output_dir: Path) -> None` — `config` is the pytest config object, needed for `rootdir`
- File paths in all output: relative to `config.rootdir`, POSIX forward-slash — `Path(abs_path).relative_to(Path(str(config.rootdir))).as_posix()`; if `relative_to` raises `ValueError` (path outside rootdir), fall back to the absolute path as a POSIX string
- Output files: `coverage-stats.json` and `coverage-stats.csv` written inside `output_dir`; create `output_dir` with `output_dir.mkdir(parents=True, exist_ok=True)` before writing
- Canonical JSON schema (from architecture — field names are frozen):
  ```json
  {
    "files": {
      "<rel_path>": {
        "lines": {
          "<lineno>": {
            "incidental_executions": 0, "deliberate_executions": 0,
            "incidental_asserts": 0, "deliberate_asserts": 0
          }
        },
        "summary": {
          "total_lines": 0,
          "incidental_coverage_pct": 0.0, "deliberate_coverage_pct": 0.0,
          "incidental_assert_density": 0.0, "deliberate_assert_density": 0.0
        }
      }
    }
  }
  ```
- Summary calculations:
  - `total_lines` = count of traced lines for that file
  - `incidental_coverage_pct` = `lines_with_incidental_executions_gt_0 / total_lines * 100.0` (0.0 if total_lines == 0)
  - `deliberate_coverage_pct` = `lines_with_deliberate_executions_gt_0 / total_lines * 100.0`
  - `incidental_assert_density` = `sum(ld.incidental_asserts) / total_lines` (0.0 if total_lines == 0)
  - `deliberate_assert_density` = `sum(ld.deliberate_asserts) / total_lines`
- Canonical CSV column order: `file,lineno,incidental_executions,deliberate_executions,incidental_asserts,deliberate_asserts`; written with `csv.writer`; UTF-8 encoding; newline=`""` (standard csv.writer requirement)
- CLI options added to `pytest_addoption`:
  - `--coverage-stats-format`: type `str`, default `""`, help text lists `html,json,csv`
  - `--coverage-stats-output`: type `str`, default `"coverage-stats-report"`
- Ini keys added: `coverage_stats_format` (default `""`), `coverage_stats_output_dir` (default `"coverage-stats-report"`)
- Format resolution: CLI flag takes precedence over ini key; parse by splitting on `,` and stripping whitespace; ignore empty tokens
- In `pytest_sessionfinish`: stop tracer first, then for each format token call the matching reporter; skip `html` silently (implemented in next story); output_dir resolved as `Path(output_dir_str).resolve()`
- stdlib + pytest only

**Ask First:**
- If `config.rootdir` type differs between pytest 7 and pytest 8 in a way that breaks the `Path(str(config.rootdir))` pattern

**Never:**
- Import `html.py` reporter in this story — HTML is next story
- Round summary float fields to a fixed number of decimal places in the data structure (let `json.dumps` handle float repr)
- Use `os.path` — use `pathlib.Path`
- Modify `store.py`

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Empty store, json format | `store._data == {}` | `{"files": {}}` written to `coverage-stats.json` | — |
| Single file, two lines | `("/abs/src/foo.py", 1)` and `("/abs/src/foo.py", 3)` | JSON has `"src/foo.py"` key with both lines; `total_lines: 2` | — |
| Path outside rootdir | abs_path not under rootdir | POSIX absolute path used as key, no crash | `ValueError` caught, fallback to abs posix |
| `--coverage-stats-format=json,csv` | both tokens | both `coverage-stats.json` and `coverage-stats.csv` written | — |
| Format token `html` | format includes `html` | silently skipped (no error, no file written) | — |
| Output dir does not exist | first run | dir created via `mkdir(parents=True, exist_ok=True)` | — |

</frozen-after-approval>

## Code Map

- `src/coverage_stats/reporters/json_reporter.py` — implement `write_json`; replace stub
- `src/coverage_stats/reporters/csv_reporter.py` — implement `write_csv`; replace stub
- `src/coverage_stats/plugin.py` — add two CLI options + two ini keys; update `pytest_sessionfinish` to stop tracer then call reporters
- `tests/unit/test_reporters/test_json.py` — unit tests for JSON output
- `tests/unit/test_reporters/test_csv.py` — unit tests for CSV output

## Tasks & Acceptance

**Execution:**
- [ ] `src/coverage_stats/reporters/json_reporter.py` -- IMPLEMENT -- replace stub with `write_json(store, config, output_dir: Path) -> None`: iterate `store._data` grouped by file path; build canonical JSON structure with per-line data + summary; write to `output_dir / "coverage-stats.json"` via `json.dumps(indent=2)`
- [ ] `src/coverage_stats/reporters/csv_reporter.py` -- IMPLEMENT -- replace stub with `write_csv(store, config, output_dir: Path) -> None`: iterate `store._data` sorted by `(rel_path, lineno)`; write header + rows via `csv.writer`; file opened with `encoding="utf-8", newline=""`
- [ ] `src/coverage_stats/plugin.py` -- UPDATE -- add `--coverage-stats-format` addoption (str, default `""`), `--coverage-stats-output` addoption (str, default `"coverage-stats-report"`), and matching `addini` keys; update `pytest_sessionfinish` to resolve format+output_dir, stop tracer, then call reporters
- [ ] `tests/unit/test_reporters/test_json.py` -- CREATE -- tests: empty store produces `{"files":{}}`, single-file multi-line structure, summary calculations, path outside rootdir fallback, lineno keys are strings in JSON
- [ ] `tests/unit/test_reporters/test_csv.py` -- CREATE -- tests: empty store writes header only, correct column order, rows sorted by file then lineno, path outside rootdir fallback

**Acceptance Criteria:**
- Given a store with data for `src/foo.py`, when `write_json` runs with `output_dir`, then `output_dir/coverage-stats.json` contains a `files` key with `"src/foo.py"` as a sub-key
- Given a store with 2 lines for a file, 1 with `deliberate_executions=5`, when `write_json` runs, then `deliberate_coverage_pct == 50.0`
- Given a store with data, when `write_csv` runs, then the first row is the header `file,lineno,incidental_executions,deliberate_executions,incidental_asserts,deliberate_asserts`
- Given `--coverage-stats-format=json,csv`, when `pytest_sessionfinish` runs, then both output files are created
- Given `--coverage-stats-format=html`, when `pytest_sessionfinish` runs, then no error is raised and no file is written for html
- Given `pytest tests/unit/test_reporters/ -v`, all tests pass

## Design Notes

**Grouping `store._data` by file:**
```python
from collections import defaultdict
files: dict[str, dict] = defaultdict(dict)
for (abs_path, lineno), ld in store._data.items():
    try:
        rel = Path(abs_path).relative_to(Path(str(config.rootdir))).as_posix()
    except ValueError:
        rel = Path(abs_path).as_posix()
    files[rel][lineno] = ld
```

**Format resolution in `pytest_sessionfinish`:**
```python
fmt_str = config.getoption("--coverage-stats-format") or config.getini("coverage_stats_format")
formats = [f.strip() for f in fmt_str.split(",") if f.strip()]
out_str = config.getoption("--coverage-stats-output") or config.getini("coverage_stats_output_dir")
output_dir = Path(out_str).resolve()
```

## Verification

**Commands:**
- `.venv/bin/pytest tests/unit/test_reporters/ -v` -- expected: all tests pass
- `.venv/bin/ruff check src/coverage_stats/reporters/json_reporter.py src/coverage_stats/reporters/csv_reporter.py src/coverage_stats/plugin.py` -- expected: exit 0
