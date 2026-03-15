---
stepsCompleted: [step-01-init, step-02-context, step-03-starter, step-04-decisions, step-05-patterns, step-06-structure, step-07-validation, step-08-complete]
lastStep: 8
status: 'complete'
completedAt: '2026-03-15'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/product-brief-coverage-stats-2026-03-15.md
  - _bmad-output/planning-artifacts/research/technical-coverage-py-html-reporting-extensibility-research-2026-03-15.md
workflowType: 'architecture'
project_name: 'coverage-stats'
user_name: 'Vlad'
date: '2026-03-15'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**

36 FRs across 7 capability areas:

| Capability area | Key FRs |
|---|---|
| `@covers` decorator & reference resolution | FR1–FR8: decorator syntax (objects, dotted strings, lists, class-level), lazy resolution just before test run, `CoverageStatsResolutionError` on failure, test-level failure with suite continuation |
| Profiler | FR9–FR10: custom `sys.settrace` tracer, source-directory scoping |
| Assert counting | FR11: `pytest_assertion_pass` hook integration; assert totals distributed across all lines executed during that test |
| Metrics | FR12–FR18: four per-line counters (incidental executions, deliberate executions, incidental assert density, deliberate assert density); deliberate/incidental split keyed by `@covers` membership |
| HTML reporting | FR19–FR29: self-contained static bundle; folder-collapsible index with per-folder aggregated stats; per-file line-level view; no CDN |
| JSON/CSV export | FR30–FR33: complete metric set; machine-readable; usable in CI without additional tooling |
| pytest integration | FR34–FR36: `--coverage-stats` flag; `pyproject.toml` / `pytest.ini` config; debugger coexistence via `sys.settrace` chaining |

**Non-Functional Requirements:**

| NFR | Requirement |
|---|---|
| NFR1 | ≤2× test-suite wall-clock overhead |
| NFR4 | Zero missed line attributions |
| NFR8 | CPython 3.9–3.13 |
| NFR9 | pytest 7.x and 8.x |
| NFR10 | stdlib + pytest only — zero third-party dependencies |

**Scale & Complexity:**

- Primary domain: Python CLI/library tool — pytest plugin
- Complexity level: **medium** — single-process Python library with a non-trivial tracing subsystem and optional multi-process coordination
- Estimated architectural components: 5 primary (Profiler, Decorator/Resolver, Assert Counter, Session Store, Report Generator)

### Technical Constraints & Dependencies

| Constraint | Source |
|---|---|
| CPython 3.9–3.13 | NFR8 |
| pytest 7.x and 8.x | NFR9 |
| stdlib + pytest only (zero third-party deps) | NFR10 |
| ≤2× test-suite wall-clock overhead | NFR1 |
| Zero missed line attributions | NFR4 |
| No dependency on coverage.py | Product brief |
| Single `sys.settrace` slot — must chain with existing trace function | FR36 |
| xdist compatibility — worker→controller data transport via `workeroutput` | This session |
| `pytest-xdist` is optional — graceful degradation when not installed | This session |

### Cross-Cutting Concerns Identified

1. **Test context tracking** — the profiler must always know which test is currently executing and whether it is deliberate or incidental for any given code unit; state must be maintained accurately across setup/call/teardown phases.

2. **`sys.settrace` chaining** — at plugin startup, any existing trace function (pdb, pydevd) must be detected and stored; the custom tracer must call through to it on every event.

3. **Assert attribution** — `pytest_assertion_pass` fires per passing assertion; the system correlates to the active test and accumulates counts. At test teardown, the total is distributed to all lines executed during that test's call phase (deliberate or incidental bucket).

4. **Source file scoping** — the profiler must filter to only instrument files within the configured `source` directories, ignoring test files, stdlib, and third-party packages.

5. **Self-contained HTML output** — the report bundle must embed all CSS/JS inline (no CDN); must render correctly as a CI artifact opened from a local filesystem path.

6. **xdist worker/controller split** — the plugin detects whether it is running as a worker or controller (via `config.workerinput` presence). Workers run the full profiler + assert counter stack and serialise their `SessionStore` into `config.workeroutput` at session end. The controller receives worker payloads via `pytest_testnodedown`, merges them additively, then runs report generation once at its own `pytest_sessionfinish`. Non-xdist runs behave as combined worker+controller.

## Starter Template Evaluation

### Primary Technology Domain

Python library / pytest plugin. No framework starter applies. Project structure and packaging tooling are established manually following current Python Packaging Authority (PyPA) best practices.

### Starter Options Considered

| Option | Build backend | Scaffold tool | Notes |
|---|---|---|---|
| Hatch | hatchling | `hatch new` | PyPA-endorsed, modern; adds contributor tooling dep |
| Flit | flit_core | `flit init` | Too minimal for plugin entry-points |
| Manual + setuptools | setuptools | None | Universal, zero extra tooling dep, entry-points well-documented |

### Selected Approach: Manual `src/` layout with `setuptools` backend

**Rationale:** Maximum compatibility, no contributor tooling barrier, well-documented pytest plugin entry-point pattern (`pytest11`), enforced import isolation via `src/` layout.

**Project Initialization:**

No scaffold command. First implementation story creates the following structure directly:

```
coverage-stats/
├── src/
│   └── coverage_stats/
│       ├── __init__.py
│       ├── plugin.py          # pytest plugin entry point
│       ├── profiler.py        # sys.settrace tracer
│       ├── covers.py          # @covers decorator + resolver
│       ├── store.py           # SessionStore (in-memory accumulator)
│       ├── assert_counter.py  # pytest_assertion_pass integration
│       └── reporters/
│           ├── html.py
│           ├── json_reporter.py
│           └── csv_reporter.py
├── tests/
├── pyproject.toml
└── README.md
```

**Architectural Decisions Established by This Structure:**

**Language & Runtime:**
Python 3.9–3.13; `from __future__ import annotations` for forward-reference compat across the supported range.

**Build Tooling:**
`setuptools` >= 61 with PEP 517/518 `pyproject.toml`. Entry-point:
`[project.entry-points."pytest11"] coverage-stats = "coverage_stats.plugin"`.

**Testing Framework:**
pytest (already the runtime dependency); test suite lives in `tests/` and is excluded from the distribution package.

**Code Organisation:**
`src/` layout — prevents accidental imports from repo root; each major subsystem is a single module at the `coverage_stats/` level; reporters are grouped in a `reporters/` subpackage.

**Development Tooling (contributor-only, not runtime deps):**
ruff (lint + format), mypy (type checking), tox or nox for multi-Python CI matrix.

**Note:** Project scaffolding (creating `pyproject.toml`, `src/` layout, and stub modules) should be the first implementation story.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Data model for SessionStore (Decision 1)
- @covers resolver canonical form and expansion rules (Decision 2)
- Profiler phase tracking mechanism (Decision 3)

**Important Decisions (Shape Architecture):**
- HTML templating approach within stdlib constraint (Decision 4)
- Configuration via pytest's config system (Decision 5)

**Deferred Decisions (Post-MVP):**
- Historical trend tracking (out of scope per PRD)
- Branch-level coverage (out of scope per PRD)

### Data Model & Session Store

- Per-line value: `dataclass` with four `int` fields:
  `incidental_executions`, `deliberate_executions`,
  `incidental_asserts`, `deliberate_asserts`
- Store keyed by `(abs_file_path: str, lineno: int)`
- xdist serialisation: dataclass → `dict` → JSON string in
  `config.workeroutput["coverage_stats_data"]`
- Controller merge: additive sum per `(file, lineno)` key across all worker payloads

### `@covers` Reference Resolution

- Dotted strings: resolved via `importlib.import_module` + `getattr` chain
- Python object references: used directly
- Canonical form: `frozenset[tuple[str, int]]` — every `(abs_file_path, lineno)`
  in the target function or class body, computed via
  `inspect.getsourcefile` + `inspect.getsourcelines`
- Class expansion: class body lines + all method lines via
  `inspect.getmembers(cls, predicate=inspect.isfunction)`
- Resolved set stored on test item as `item._covers_lines` at `pytest_runtest_setup`
- O(1) set-membership check per executed line in the profiler hot path
- Resolution failure → `CoverageStatsResolutionError` raised via `pytest.fail()`;
  test fails, suite continues (FR7, FR8)

### Profiler Design

- `sys.settrace` registered at `pytest_configure`; existing trace function detected
  and chained on every event (FR36 debugger coexistence)
- Shared `ProfilerContext` object holds:
  - `current_test_item: pytest.Item | None`
  - `current_phase: Literal["setup", "call", "teardown"] | None`
  - `current_assert_count: int`
  - `source_dirs: list[str]` (normalised absolute paths)
- Phase flag set by `pytest_runtest_setup/call/teardown` hooks
- Line accumulation occurs **only during `call` phase**
- Source scoping: executed file must have a normalised path that starts with
  one of the configured `source_dirs` prefixes; all other files skipped
- `pytest_assertion_pass` hook increments `current_assert_count` during call phase;
  count distributed to all lines executed in that test at `pytest_runtest_teardown`

### HTML Report Generation

- f-string composition with helper functions in `reporters/html.py`
- Helper functions: `render_file_row`, `render_line`, `render_folder_section`,
  `render_index_page`, `render_file_page`
- CSS and JS embedded as module-level string constants (no CDN, no external files)
- Folder-collapsible behaviour implemented with vanilla JS (no framework)
- Output: one `index.html` + one `<module_path>.html` per measured file,
  all written to the configured output directory

### Configuration & Plugin Registration

- Plugin auto-registered via `[project.entry-points."pytest11"]` in `pyproject.toml`
- All config declared via `pytest_addoption` (CLI flags) and `addini`
  (`pyproject.toml` / `pytest.ini` keys) — pytest handles file lookup natively
- No direct TOML parsing; no `tomllib` compatibility shim needed
- CLI flags: `--coverage-stats`, `--coverage-stats-output=DIR`,
  `--coverage-stats-format=html,json,csv`
- Config keys: `coverage_stats_source`, `coverage_stats_output_dir`,
  `coverage_stats_format`

### Distribution & CI

- Build: `python -m build` (PEP 517); `twine upload` on version tag
- CI: GitHub Actions; matrix `python × [3.9, 3.10, 3.11, 3.12, 3.13]`
  × `pytest × [">=7,<8", ">=8,<9"]`
- Versioning: PEP 440 in `pyproject.toml`;
  `__version__` exported from `coverage_stats/__init__.py`

### Decision Impact Analysis

**Implementation Sequence:**
1. `pyproject.toml` + package scaffold (enables all imports)
2. `ProfilerContext` + `SessionStore` dataclass (data foundation)
3. `@covers` decorator + resolver (populates `item._covers_lines`)
4. `sys.settrace` profiler (consumes `_covers_lines`, writes to store)
5. `pytest_assertion_pass` assert counter (increments `current_assert_count`)
6. JSON + CSV reporters (simplest output, good for integration testing)
7. HTML reporter (depends on complete store data model)
8. xdist worker/controller split (layered on top of working single-process impl)

**Cross-Component Dependencies:**
- Profiler depends on `item._covers_lines` being set by Resolver before call phase
- Assert Counter depends on Profiler's `current_assert_count` field
- All reporters depend on the final shape of the `SessionStore` dataclass
- xdist controller depends on JSON serialisability of `SessionStore`

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Python naming — all modules, functions, variables:**
- snake_case for all identifiers (Python standard)
- Module files: noun-first, describes the subsystem: `profiler.py`, `store.py`,
  `covers.py`, `assert_counter.py`, `plugin.py`
- Reporter modules: `reporters/html.py`, `reporters/json_reporter.py`,
  `reporters/csv_reporter.py` (prefix avoids shadowing stdlib `json`)
- Classes: PascalCase — `SessionStore`, `ProfilerContext`, `LineData`,
  `CoverageStatsPlugin`, `CoverageStatsResolutionError`
- Internal state fields on `ProfilerContext`:
  `current_test_item`, `current_phase`, `current_assert_count`, `source_dirs`
  (never abbreviate: not `cur_item`, not `phase`, not `cnt`)

**pytest hook implementations in `plugin.py`:**
- Name exactly as pytest specifies — no aliases, no wrappers with different names
- All hooks on a single `CoverageStatsPlugin` class registered via `pytest_configure`
- Hook ordering: `pytest_configure` → `pytest_collection_finish` →
  `pytest_runtest_setup` → `pytest_runtest_call` → `pytest_assertion_pass` →
  `pytest_runtest_teardown` → `pytest_sessionfinish`

### Structure Patterns

**Singleton context object:**
- `ProfilerContext` is instantiated once in `pytest_configure` and stored as
  `config._coverage_stats_ctx` (prefixed to avoid collision with other plugins)
- All hooks receive context by reading `config._coverage_stats_ctx`
- Never pass context as a parameter through pytest hook calls — always retrieve
  from config
- Never use a module-level global for context — retrieving from config keeps
  xdist worker isolation correct

**Data classes:**
- `LineData` is a `dataclasses.dataclass` (not `TypedDict`, not `NamedTuple`) —
  mutable fields allow in-place counter increment, no dict overhead
- `SessionStore` is a plain class wrapping `dict[tuple[str, int], LineData]` —
  not a dataclass (it has behavioural methods: `get_or_create`, `merge`, `to_dict`)
- No `__slots__` on these classes in MVP — correctness over micro-optimisation

**Plugin guard — no-op when flag absent:**
- At `pytest_configure`, check `config.getoption("--coverage-stats", default=False)`
- If False: return immediately, do NOT register `sys.settrace`, do NOT attach hooks
- This must be the first check in every hook — plugins are always loaded but must
  be silent unless activated
- Pattern: store `self._enabled: bool` on `CoverageStatsPlugin`; every hook method
  begins with `if not self._enabled: return`

**Reporters as functions, not classes:**
- Each reporter module exports a single function: `write_html(store, config, output_dir)`,
  `write_json(store, config, output_dir)`, `write_csv(store, config, output_dir)`
- No reporter class hierarchy — they are stateless transformations of `SessionStore`
- Called sequentially from `pytest_sessionfinish` after store is finalised

### Format Patterns

**JSON output field names (canonical — must not be renamed):**

```json
{
  "files": {
    "<relative_file_path>": {
      "lines": {
        "<lineno>": {
          "incidental_executions": 0,
          "deliberate_executions": 0,
          "incidental_asserts": 0,
          "deliberate_asserts": 0
        }
      },
      "summary": {
        "total_lines": 0,
        "incidental_coverage_pct": 0.0,
        "deliberate_coverage_pct": 0.0,
        "incidental_assert_density": 0.0,
        "deliberate_assert_density": 0.0
      }
    }
  }
}
```

**CSV column names (canonical order):**
`file,lineno,incidental_executions,deliberate_executions,incidental_asserts,deliberate_asserts`

**File paths in output:**
- Always stored and emitted as **relative paths** from the project root (`rootdir`)
  using forward slashes regardless of OS
- Use `pathlib.Path(abs_path).relative_to(rootdir).as_posix()` — never `os.path`
  or backslash-joined strings

**Assert density formula (canonical):**
- `deliberate_assert_density = total_deliberate_asserts_in_file / total_lines_in_file`
- `total_lines_in_file` = number of executable lines that appeared in the profiler
  trace for that file — not raw `wc -l` line count
- Must be consistent across HTML, JSON, and CSV outputs

### Error Handling Patterns

**Exception hierarchy:**
```python
class CoverageStatsError(Exception): ...
class CoverageStatsResolutionError(CoverageStatsError): ...
```

**Resolution failure:**
- Always raised via `pytest.fail(f"coverage-stats: cannot resolve @covers target ...")`,
  NOT `raise CoverageStatsResolutionError(...)` directly
- `pytest.fail()` marks the test FAILED with a clear message and lets the suite
  continue — correct pytest pattern for plugin-driven test-level failures
- Error message format:
  `"coverage-stats: cannot resolve @covers target {repr(ref)} for test {item.nodeid} — {reason}"`

**Errors inside `sys.settrace` callback:**
- Must be caught and emitted as `warnings.warn` — never raise inside a trace
  function (raises inside trace callbacks corrupt the trace stack silently)

### Process Patterns

**xdist detection helpers (use these everywhere, never inline):**
```python
def _is_xdist_worker(config) -> bool:
    return hasattr(config, "workerinput")

def _is_xdist_controller(config) -> bool:
    return not _is_xdist_worker(config) and config.pluginmanager.hasplugin("xdist")
```

**`source` not configured:**
- Profile all non-stdlib, non-site-packages files (path does not contain
  `site-packages` and is not under `sys.prefix`)
- Never fail — emit `warnings.warn` suggesting explicit `source` config

### Enforcement Guidelines

**All AI Agents MUST:**
- Import `SessionStore` and `LineData` from `coverage_stats.store` — never redefine locally
- Use `pathlib.Path` for all file path operations — never `os.path`
- Use `from __future__ import annotations` at the top of every module
- Never add third-party imports — stdlib + pytest only
- Check `self._enabled` as the first line of every hook method
- Use the canonical JSON field names exactly as specified above
- Use `pytest.fail()` (not `raise`) for `@covers` resolution errors

**Anti-Patterns to Avoid:**
- ❌ Module-level global for `ProfilerContext` — breaks xdist worker isolation
- ❌ Eager `@covers` resolution at decoration time — breaks lazy resolution contract
- ❌ Accumulating line hits during setup/teardown — contaminates call-phase data
- ❌ Using `coverage.py` internals for any purpose
- ❌ Any CDN link or external resource in HTML output
- ❌ OS-specific path separators in output files

## Project Structure & Boundaries

### Complete Project Directory Structure

```
coverage-stats/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # matrix: python 3.9–3.13 × pytest 7/8
│       └── publish.yml             # PyPI publish on version tag
├── src/
│   └── coverage_stats/
│       ├── __init__.py             # exports: covers, __version__
│       ├── plugin.py               # CoverageStatsPlugin; all pytest hook impls
│       ├── profiler.py             # sys.settrace tracer; ProfilerContext dataclass
│       ├── covers.py               # @covers decorator; CoverageStatsResolutionError
│       ├── store.py                # SessionStore; LineData dataclass
│       ├── assert_counter.py       # pytest_assertion_pass handler
│       └── reporters/
│           ├── __init__.py
│           ├── html.py             # write_html(); embedded CSS/JS constants
│           ├── json_reporter.py    # write_json()
│           └── csv_reporter.py     # write_csv()
├── tests/
│   ├── conftest.py                 # shared fixtures (pytester, sample source trees)
│   ├── unit/
│   │   ├── test_covers.py          # @covers decorator; resolution logic; error cases
│   │   ├── test_profiler.py        # sys.settrace mechanics; phase tracking; scoping
│   │   ├── test_store.py           # SessionStore CRUD; merge; serialisation
│   │   └── test_reporters/
│   │       ├── test_html.py        # HTML output structure; embedded assets
│   │       ├── test_json.py        # JSON schema; field names; path format
│   │       └── test_csv.py         # CSV column order; encoding
│   └── integration/
│       ├── test_plugin_basic.py    # end-to-end: no @covers → all incidental
│       ├── test_plugin_covers.py   # end-to-end: @covers → deliberate split
│       ├── test_plugin_xdist.py    # end-to-end: pytest-xdist worker merge
│       ├── test_plugin_disabled.py # --coverage-stats absent → no-op
│       └── test_resolution_errors.py  # bad @covers ref → test fails, suite continues
├── pyproject.toml
├── README.md
└── .gitignore
```

### Architectural Boundaries

**Module responsibilities (what each file owns — AI agents must not cross these):**

| Module | Owns | Must NOT |
|---|---|---|
| `plugin.py` | pytest hook registration; lifecycle coordination; xdist split | business logic; data structures |
| `profiler.py` | `sys.settrace` registration; line event handling; phase flag; source scoping | know about reporters or @covers resolution |
| `covers.py` | `@covers` decorator; lazy reference resolution; `CoverageStatsResolutionError` | touch `sys.settrace` or store directly |
| `store.py` | `LineData`; `SessionStore`; `merge()`; `to_dict()`; `from_dict()` | know about pytest or reporters |
| `assert_counter.py` | `pytest_assertion_pass` handler; incrementing `ProfilerContext.current_assert_count` | accumulate anything else |
| `reporters/html.py` | HTML generation; CSS/JS constants | read from config directly (receives `output_dir` as arg) |
| `reporters/json_reporter.py` | JSON serialisation; path normalisation | HTML or CSV concerns |
| `reporters/csv_reporter.py` | CSV serialisation; column ordering | HTML or JSON concerns |

**Public API (exported from `coverage_stats/__init__.py`):**
```python
from coverage_stats import covers          # decorator — the only user-facing API
from coverage_stats import __version__     # version string
```
Everything else is internal. No other names are part of the public API.

### Requirements to Structure Mapping

| FR range | Capability | Primary module |
|---|---|---|
| FR1–FR5 | `@covers` decorator syntax (objects, strings, lists, class-level) | `covers.py` |
| FR6–FR8 | Lazy resolution; error on failure; suite continues | `covers.py` + `plugin.py` |
| FR9–FR10 | Custom profiler; source scoping | `profiler.py` |
| FR11 | Assert counting via `pytest_assertion_pass` | `assert_counter.py` |
| FR12–FR18 | Four metrics; deliberate/incidental split | `store.py` + `profiler.py` |
| FR19–FR29 | HTML report: index + per-file; folder-collapsible | `reporters/html.py` |
| FR30–FR33 | JSON + CSV export | `reporters/json_reporter.py`, `reporters/csv_reporter.py` |
| FR34–FR35 | pytest plugin; CLI flags; config | `plugin.py` |
| FR36 | Debugger coexistence via `sys.settrace` chaining | `profiler.py` |
| xdist | Worker/controller split; store serialisation | `plugin.py` + `store.py` |

### Integration Points

**Internal data flow (single-process run):**

```
@covers decorator
    ↓ stores raw refs on test function
pytest_runtest_setup [plugin.py]
    ↓ calls covers.py resolver
    ↓ stores frozenset on item._covers_lines
sys.settrace callback [profiler.py]
    ↓ per-line event: check item._covers_lines membership
    ↓ writes to SessionStore [store.py]
pytest_assertion_pass [assert_counter.py]
    ↓ increments ProfilerContext.current_assert_count
pytest_runtest_teardown [plugin.py]
    ↓ distributes assert count to all lines hit in call phase
pytest_sessionfinish [plugin.py]
    ↓ calls write_html / write_json / write_csv [reporters/]
```

**xdist data flow:**

```
[worker process]
  same flow as above →
  pytest_sessionfinish (worker):
    store.to_dict() → json.dumps → config.workeroutput["coverage_stats_data"]

[controller process]
  pytest_testnodedown (per worker):
    json.loads → store.from_dict() → merge into controller SessionStore
  pytest_sessionfinish (controller):
    calls reporters with merged store
```

**External integration points:**
- `pytest` — hook protocol (only external runtime dependency)
- `pytest-xdist` — optional; detected via `config.workerinput` / plugin presence
- PyPI — distribution channel; no runtime external calls

### Test Organisation

**Unit tests** (`tests/unit/`) — test each module in isolation using pure Python; no pytest session needed for most; mock `sys.settrace` where needed

**Integration tests** (`tests/integration/`) — use pytest's `pytester` fixture to run sub-pytest sessions against minimal sample source trees; assert on generated output files and exit codes

**Fixtures** (`tests/conftest.py`):
- `sample_source_tree(tmp_path)` — creates a minimal Python package under `tmp_path/src/` for integration tests
- `pytester` — provided by pytest itself; used for all plugin integration tests

### Development Workflow

**Local development:**
```bash
pip install -e ".[dev]"          # installs package in editable mode + dev deps
pytest tests/unit/               # fast feedback loop
pytest tests/integration/        # full plugin behaviour
```

**CI (`.github/workflows/ci.yml`):**
- Matrix: `python-version: [3.9, 3.10, 3.11, 3.12, 3.13]` × `pytest-version: [">=7,<8", ">=8,<9"]`
- Steps: `pip install -e ".[dev]"` → `ruff check` → `mypy src/` → `pytest tests/`

**Release (`.github/workflows/publish.yml`):**
- Trigger: push tag matching `v*.*.*`
- Steps: `python -m build` → `twine upload dist/*` (using PyPI trusted publisher)

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
All technology choices are internally compatible. Python 3.9–3.13 support is
maintained across the full implementation: `dataclasses` (3.7+), `pathlib` (3.4+),
`importlib` and `inspect` (stdlib throughout), `from __future__ import annotations`
for type-hint compatibility. `tomllib` was explicitly avoided; configuration is
delegated to pytest's own config system, preserving 3.9–3.10 compatibility.

**Pattern Consistency:**
All implementation patterns align with architectural decisions:
- `dataclass` for `LineData` — mutable in-place increment, no dict overhead
- `pathlib.Path` mandate — cross-platform, stdlib
- `pytest.fail()` for resolution errors — correct test-level failure pattern
- Module singleton context via `config._coverage_stats_ctx` — xdist process isolation safe

**Structure Alignment:**
Module boundaries are clean and non-overlapping. `profiler.py` reads
`item._covers_lines` but does not perform resolution. Reporters receive a
finalised `SessionStore`; they do not touch pytest internals. No circular
dependencies exist between modules.

### Requirements Coverage Validation ✅

All 36 functional requirements (FR1–FR36) and 5 key NFRs are architecturally
supported. See the FR → module mapping table in the Project Structure section.

All FR capability areas are addressed:
- `@covers` decorator API (FR1–FR8): `covers.py` + `plugin.py`
- Custom profiler + scoping (FR9–FR10): `profiler.py`
- Assert counting (FR11): `assert_counter.py`
- Four metrics + deliberate/incidental (FR12–FR18): `store.py` + `profiler.py`
- HTML report (FR19–FR29): `reporters/html.py`
- JSON + CSV (FR30–FR33): `reporters/`
- Plugin, CLI, config (FR34–FR35): `plugin.py`
- Debugger coexistence (FR36): `profiler.py` sys.settrace chaining

### Gap Analysis Results

**No critical blocking gaps.**

**Important constraint — documented as a known limitation:**

`pytest_assertion_pass` only fires when pytest assertion rewriting is active
(the default mode). If a user runs with `--assert=plain`, the hook never fires
and assert counts will be zero. This must be documented in README and plugin
startup output as: "Assert density requires pytest assertion rewriting (default).
Running with `--assert=plain` disables assert counting."

No architectural change is required — `pytest_assertion_pass` is the correct
mechanism. This is a documentation and user-communication gap only.

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed (medium — tracing subsystem + optional xdist)
- [x] Technical constraints identified (zero deps, CPython 3.9–3.13, pytest 7/8)
- [x] Cross-cutting concerns mapped (6 concerns documented)

**✅ Architectural Decisions**
- [x] Critical decisions documented (SessionStore model, resolver canonical form, phase tracking)
- [x] Technology stack fully specified (setuptools, src/ layout, ruff, mypy)
- [x] Integration patterns defined (xdist worker/controller split)
- [x] Performance considerations addressed (O(1) set-membership, call-phase only)

**✅ Implementation Patterns**
- [x] Naming conventions established (snake_case, module naming, class naming)
- [x] Structure patterns defined (singleton context, reporter functions, plugin guard)
- [x] Format patterns specified (canonical JSON schema, CSV columns, path format)
- [x] Process patterns documented (xdist detection helpers, resolution error pattern)
- [x] Anti-patterns documented (6 explicit anti-patterns)

**✅ Project Structure**
- [x] Complete directory structure defined
- [x] All module boundaries and responsibilities documented
- [x] Public API surface defined (`covers`, `__version__` only)
- [x] FR → module mapping complete
- [x] Internal data flow documented (single-process + xdist)
- [x] Test organisation defined (unit + integration with `pytester`)
- [x] CI/CD pipeline specified (GitHub Actions matrix)

### Architecture Readiness Assessment

**Overall Status: READY FOR IMPLEMENTATION**

**Confidence Level: High**

**Key Strengths:**
- Zero-dependency constraint enforced through every layer — no risk of third-party dep creep
- Clear module boundaries with explicit "must NOT" rules prevent scope bleed
- xdist compatibility is a first-class concern, not an afterthought
- Canonical output schemas (JSON, CSV) are locked down to prevent AI agent divergence
- Lazy `@covers` resolution is architecturally enforced at the hook level

**Areas for Future Enhancement:**
- Branch-level deliberate coverage (post-MVP per PRD)
- Historical trend tracking via JSON export comparison (post-MVP)
- IDE integration (post-MVP)

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all module boundary rules in the "Architectural Boundaries" table exactly
- Use `pytest.fail()` (not `raise`) for resolution errors
- Check `self._enabled` as the first line of every hook method
- Use canonical JSON field names as specified — do not rename
- Use `pathlib.Path` for all path operations
- Store `ProfilerContext` on `config._coverage_stats_ctx` — never as a global

**First Implementation Story:**
Project scaffold — create `pyproject.toml`, `src/coverage_stats/` package skeleton,
stub modules, `tests/` structure, and `.github/workflows/ci.yml`. This unblocks
all subsequent stories.

