# Architecture: coverage-stats

A pytest plugin that tracks **deliberate vs. incidental line coverage** per test, with assertion density metrics, and generates HTML, JSON, and CSV reports.

---

## Table of Contents

1. [Project Structure](#project-structure)
2. [Component Overview](#component-overview)
3. [Class Diagram](#class-diagram)
4. [Data Model](#data-model)
5. [Sequence Diagrams](#sequence-diagrams)
   - [Single-Process Test Run](#single-process-test-run)
   - [xdist Parallel Run](#xdist-parallel-run)
   - [Line Execution Recording](#line-execution-recording)
   - [@covers Resolution](#covers-resolution)
6. [State Machine: Plugin Lifecycle](#state-machine-plugin-lifecycle)
7. [Flowchart: Line Categorization](#flowchart-line-categorization)
8. [Component Interaction](#component-interaction)

---

## Project Structure

```
coverage-stats/
├── src/coverage_stats/
│   ├── __init__.py              # Package entry point, exports @covers
│   ├── plugin.py                # Main pytest plugin — lifecycle hooks
│   ├── covers.py                # @covers decorator & reference resolver
│   ├── profiler.py              # sys.settrace line tracer
│   ├── store.py                 # Session store for line metrics
│   ├── assert_counter.py        # Assert counting & distribution
│   ├── executable_lines.py      # AST-based executable statement detection
│   └── reporters/
│       ├── __init__.py
│       ├── json_reporter.py     # JSON export
│       ├── csv_reporter.py      # CSV export
│       └── html.py              # HTML report generation
├── tests/
│   ├── unit/                    # Unit tests per module
│   ├── integration/             # Integration tests via pytester
│   └── conftest.py
└── pyproject.toml               # Build config, pytest11 entry point
```

---

## Component Overview

| Module | Role |
|---|---|
| `plugin.py` | Central orchestrator; implements all pytest hooks |
| `profiler.py` | Installs `sys.settrace` to record executed lines per test |
| `covers.py` | `@covers` decorator + lazy resolver that maps refs to `(path, lineno)` sets |
| `store.py` | `SessionStore` — maps `(path, lineno)` → `LineData` metrics |
| `assert_counter.py` | Counts passing assertions and distributes them across hit lines |
| `executable_lines.py` | AST-walks source files to find executable (non-comment) statements |
| `reporters/html.py` | Generates self-contained HTML index + per-file detail pages |
| `reporters/json_reporter.py` | Exports metrics as structured JSON |
| `reporters/csv_reporter.py` | Exports raw line-level data as CSV |

---

## Class Diagram

```mermaid
classDiagram
    class CoverageStatsPlugin {
        +ProfilerContext ctx
        +SessionStore store
        +LineTracer tracer
        +bool is_worker
        +bool is_controller
        +pytest_addoption()
        +pytest_configure()
        +pytest_sessionstart()
        +pytest_runtest_setup()
        +pytest_runtest_call()
        +pytest_assertion_pass()
        +pytest_runtest_teardown()
        +pytest_testnodedown()
        +pytest_sessionfinish()
    }

    class ProfilerContext {
        +Item current_test_item
        +str current_phase
        +int current_assert_count
        +list~str~ source_dirs
        +set current_test_lines
        +set pre_test_lines
    }

    class LineTracer {
        -ProfilerContext _ctx
        -SessionStore _store
        -TraceFunc _prev_trace
        -dict _scope_cache
        +start()
        +stop()
        -_trace(frame, event, arg)
        -_make_local_trace(filename, prev_local)
        -_in_scope(filename) bool
        -_resolve_filename(co_filename) str
    }

    class SessionStore {
        -dict~str, LineData~ _data
        +get_or_create(path, lineno) LineData
        +merge(other)
        +to_dict() dict
        +from_dict(d)$
        +items() Iterable
    }

    class LineData {
        +int incidental_executions
        +int deliberate_executions
        +int incidental_asserts
        +int deliberate_asserts
        +int incidental_tests
        +int deliberate_tests
    }

    class CoversDecorator {
        +__call__(refs) decorator
        +resolve_covers(item)
        -_resolve_ref(ref) object
        -_resolve_dotted_string(s) object
        -_get_source_lines(obj) set
    }

    class AssertCounter {
        +record_assertion(ctx)
        +distribute_asserts(ctx, store)
    }

    class ExecutableLines {
        +get_executable_lines(path) set~int~
    }

    class HTMLReporter {
        +write_html(store, source_root, output_dir)
        -_write_index(files, output_dir)
        -_write_file_page(path, lines, output_dir)
        -_get_partial_branches(path, executed_lines) set
        -_build_folder_tree(files) dict
    }

    class JSONReporter {
        +write_json(store, source_root, output_dir)
    }

    class CSVReporter {
        +write_csv(store, source_root, output_dir)
    }

    CoverageStatsPlugin --> ProfilerContext : owns
    CoverageStatsPlugin --> SessionStore : owns
    CoverageStatsPlugin --> LineTracer : owns
    CoverageStatsPlugin --> CoversDecorator : uses
    CoverageStatsPlugin --> AssertCounter : uses
    CoverageStatsPlugin --> HTMLReporter : calls
    CoverageStatsPlugin --> JSONReporter : calls
    CoverageStatsPlugin --> CSVReporter : calls
    LineTracer --> ProfilerContext : reads
    LineTracer --> SessionStore : writes
    AssertCounter --> ProfilerContext : reads/writes
    AssertCounter --> SessionStore : writes
    CoversDecorator --> ExecutableLines : uses
    SessionStore "1" *-- "many" LineData : contains
```

---

## Data Model

```mermaid
erDiagram
    SESSION_STORE {
        string key "path + NUL + lineno"
    }

    LINE_DATA {
        int incidental_executions
        int deliberate_executions
        int incidental_asserts
        int deliberate_asserts
        int incidental_tests
        int deliberate_tests
    }

    TEST_ITEM {
        string nodeid
        frozenset covers_lines "(path, lineno) pairs"
    }

    PROFILER_CONTEXT {
        string current_phase "setup | call | teardown | None"
        int current_assert_count
        set current_test_lines
        set pre_test_lines
    }

    REPORT_FILE {
        string relative_path
        int total_stmts
        float incidental_coverage_pct
        float deliberate_coverage_pct
        float incidental_assert_density
        float deliberate_assert_density
    }

    SESSION_STORE ||--o{ LINE_DATA : "stores per (path, lineno)"
    TEST_ITEM ||--o{ LINE_DATA : "deliberate lines reference"
    PROFILER_CONTEXT ||--|| TEST_ITEM : "tracks current"
    REPORT_FILE ||--o{ LINE_DATA : "aggregates"
```

---

## Sequence Diagrams

### Single-Process Test Run

```mermaid
sequenceDiagram
    participant pytest
    participant Plugin
    participant Tracer
    participant Store
    participant Covers
    participant AssertCounter
    participant Reporters

    pytest->>Plugin: pytest_configure()
    Plugin->>Store: create SessionStore
    Plugin->>Tracer: create LineTracer

    pytest->>Plugin: pytest_sessionstart()
    Plugin->>Tracer: start() → sys.settrace

    loop For each test
        pytest->>Plugin: pytest_runtest_setup(item)
        Plugin->>Covers: resolve_covers(item)
        Covers-->>Plugin: item._covers_lines = frozenset[(path,lineno)]
        Plugin->>Plugin: phase = "setup", reset counters

        pytest->>Plugin: pytest_runtest_call(item)
        Plugin->>Plugin: phase = "call"

        Note over Tracer,Store: Python executes test body
        Tracer->>Store: record line (deliberate or incidental)

        pytest->>Plugin: pytest_assertion_pass()
        Plugin->>AssertCounter: record_assertion(ctx)

        pytest->>Plugin: pytest_runtest_teardown(item)
        Plugin->>AssertCounter: distribute_asserts(ctx, store)
        Plugin->>Plugin: phase = "teardown"
    end

    pytest->>Plugin: pytest_sessionfinish()
    Plugin->>Tracer: stop()
    Plugin->>Store: flush pre_test_lines (as incidental)
    Plugin->>Reporters: write_json(store)
    Plugin->>Reporters: write_csv(store)
    Plugin->>Reporters: write_html(store)
```

---

### xdist Parallel Run

```mermaid
sequenceDiagram
    participant Controller
    participant Worker1
    participant Worker2
    participant Store as ControllerStore
    participant Reporters

    Note over Controller: Detects xdist controller (no workerinput)
    Controller->>Store: create empty SessionStore (no tracer)

    par Worker 1
        Worker1->>Worker1: pytest_configure() — full setup
        Worker1->>Worker1: pytest_sessionstart() → sys.settrace
        Worker1->>Worker1: run assigned tests
        Worker1->>Worker1: pytest_sessionfinish()
        Worker1->>Worker1: serialize store → workeroutput["coverage_stats_data"]
    and Worker 2
        Worker2->>Worker2: pytest_configure() — full setup
        Worker2->>Worker2: pytest_sessionstart() → sys.settrace
        Worker2->>Worker2: run assigned tests
        Worker2->>Worker2: pytest_sessionfinish()
        Worker2->>Worker2: serialize store → workeroutput["coverage_stats_data"]
    end

    Worker1->>Controller: pytest_testnodedown(node)
    Controller->>Store: merge(worker1_store)

    Worker2->>Controller: pytest_testnodedown(node)
    Controller->>Store: merge(worker2_store)

    Controller->>Reporters: write_json(merged_store)
    Controller->>Reporters: write_csv(merged_store)
    Controller->>Reporters: write_html(merged_store)
```

---

### Line Execution Recording

```mermaid
sequenceDiagram
    participant Python as Python Runtime
    participant Tracer as LineTracer
    participant Cache as _scope_cache
    participant Store as SessionStore
    participant Ctx as ProfilerContext

    Python->>Tracer: _trace(frame, "call", None)
    Tracer->>Cache: _in_scope(co_filename)?
    alt not cached
        Cache-->>Tracer: miss
        Tracer->>Tracer: resolve abs path
        Tracer->>Cache: store result
    end
    Cache-->>Tracer: (resolved_path, in_scope)

    alt in scope
        Tracer-->>Python: return _make_local_trace(filename, prev_local)
        Python->>Tracer: local(frame, "line", None)
        Tracer->>Ctx: read phase, current_test_item, covers_lines
        alt phase == "call"
            alt (filename, lineno) in covers_lines
                Tracer->>Store: ld.deliberate_executions += 1
            else
                Tracer->>Store: ld.incidental_executions += 1
            end
            Tracer->>Ctx: current_test_lines.add((filename, lineno))
        else phase is None
            Tracer->>Ctx: pre_test_lines.add((filename, lineno))
        end
        Tracer-->>Python: call prev_local (chain to coverage.py)
    else out of scope
        Tracer-->>Python: return None (no per-line tracing)
    end
```

---

### @covers Resolution

```mermaid
sequenceDiagram
    participant Test as Test Function
    participant Decorator as @covers
    participant Plugin
    participant Resolver as covers.py
    participant ImportLib
    participant Inspect
    participant AST as executable_lines.py

    Test->>Decorator: @covers("mymodule.MyClass.method")
    Decorator->>Test: store _covers_refs on function

    Plugin->>Resolver: resolve_covers(item)
    Resolver->>Resolver: find _covers_refs on item.function / item.cls

    loop for each ref
        alt ref is string
            Resolver->>ImportLib: import_module(module_part)
            ImportLib-->>Resolver: module object
            Resolver->>Resolver: getattr chain for attribute parts
        else ref is object
            Resolver->>Resolver: use directly
        end

        Resolver->>Inspect: getsourcefile(obj)
        Inspect-->>Resolver: abs_path
        Resolver->>Inspect: getsourcelines(obj)
        Inspect-->>Resolver: (source_lines, start_lineno)
        Resolver->>AST: get_executable_lines(abs_path)
        AST->>AST: ast.parse() → walk → collect stmt linenos
        AST->>AST: exclude docstring lines
        AST-->>Resolver: set of executable linenos
        Resolver->>Resolver: filter to executable lines in range
    end

    Resolver-->>Plugin: item._covers_lines = frozenset[(abs_path, lineno)]
```

---

## State Machine: Plugin Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Unconfigured

    Unconfigured --> Configured : pytest_configure()\ncreate ctx, store, tracer

    Configured --> Tracing : pytest_sessionstart()\ntracer.start()

    state Tracing {
        [*] --> Idle

        Idle --> Setup : pytest_runtest_setup()\nresolve_covers, phase="setup"

        Setup --> CallPhase : pytest_runtest_call()\nphase="call"

        state CallPhase {
            [*] --> Recording
            Recording --> Recording : line executed → store
            Recording --> Recording : assertion_pass → count++
        }

        CallPhase --> Teardown : pytest_runtest_teardown()\ndistribute_asserts, phase="teardown"

        Teardown --> Idle : test complete
    }

    Tracing --> Reporting : pytest_sessionfinish()\ntracer.stop(), flush pre_test_lines

    Reporting --> [*] : write HTML / JSON / CSV
```

---

## Flowchart: Line Categorization

```mermaid
flowchart TD
    A[Python executes a line] --> B{Phase?}

    B -- "call" --> C{file in scope?}
    B -- "None" --> P[Add to pre_test_lines\nmodule-level import code]
    B -- "setup / teardown" --> Z[Ignore]

    C -- No --> Z
    C -- Yes --> D{line in\nitem._covers_lines?}

    D -- Yes --> E[deliberate_executions += 1]
    D -- No --> F[incidental_executions += 1]

    E --> G[Add to current_test_lines]
    F --> G

    G --> H[At teardown: distribute_asserts]
    H --> I{line in\nitem._covers_lines?}

    I -- Yes --> J[deliberate_asserts += count\ndeliberate_tests += 1]
    I -- No --> K[incidental_asserts += count\nincidental_tests += 1]

    P --> L[At session end:\nflush as incidental]
```

---

## Component Interaction

```mermaid
graph TD
    subgraph pytest["pytest Runtime"]
        hooks["Lifecycle Hooks\n(configure, setup, call, teardown, finish)"]
    end

    subgraph plugin["plugin.py — CoverageStatsPlugin"]
        core["Central Orchestrator"]
    end

    subgraph tracing["Tracing Layer"]
        tracer["profiler.py\nLineTracer\n(sys.settrace)"]
        ctx["ProfilerContext\n(phase, counts, lines)"]
    end

    subgraph analysis["Analysis Layer"]
        covers["covers.py\n@covers Decorator\n+ Resolver"]
        asserts["assert_counter.py\nAssertion Distribution"]
        exlines["executable_lines.py\nAST Statement Finder"]
    end

    subgraph storage["Storage Layer"]
        store["store.py\nSessionStore\n(path, lineno) → LineData"]
    end

    subgraph reporting["Reporting Layer"]
        html["reporters/html.py\nHTML Report"]
        json["reporters/json_reporter.py\nJSON Export"]
        csv["reporters/csv_reporter.py\nCSV Export"]
    end

    subgraph output["Output"]
        htmlout["index.html\n+ file pages"]
        jsonout["coverage-stats.json"]
        csvout["coverage-stats.csv"]
    end

    hooks -->|hooks fire| core
    core -->|creates / controls| tracer
    core -->|creates / controls| ctx
    core -->|resolve_covers| covers
    core -->|distribute_asserts| asserts
    covers -->|get_executable_lines| exlines
    tracer -->|reads phase| ctx
    tracer -->|writes LineData| store
    asserts -->|reads counts| ctx
    asserts -->|writes LineData| store
    core -->|session finish| html
    core -->|session finish| json
    core -->|session finish| csv
    html --> htmlout
    json --> jsonout
    csv --> csvout
```
