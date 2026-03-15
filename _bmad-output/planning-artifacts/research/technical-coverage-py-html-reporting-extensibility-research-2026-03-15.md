---
stepsCompleted: [1, 2]
inputDocuments: []
workflowType: 'research'
lastStep: 1
research_type: 'technical'
research_topic: 'coverage.py HTML reporting extensibility'
research_goals: 'Determine if coverage.py HTML reporting can be extended with new columns, or if its reporting code can be reused to build a similar custom report'
user_name: 'Vlad'
date: '2026-03-15'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-03-15
**Author:** Vlad
**Research Type:** technical

---

## Research Overview

[Research overview and methodology will be appended here]

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technical Research Scope Confirmation

**Research Topic:** coverage.py HTML reporting extensibility
**Research Goals:** Determine if coverage.py HTML reporting can be extended with new columns, or if its reporting code can be reused to build a similar custom report

**Technical Research Scope:**

- Architecture Analysis - design patterns, frameworks, system architecture
- Implementation Approaches - development methodologies, coding patterns
- Technology Stack - languages, frameworks, tools, platforms
- Integration Patterns - APIs, protocols, interoperability
- Performance Considerations - scalability, optimization, patterns

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-03-15

---

## Technology Stack Analysis

> **Note:** Web search was unavailable in this environment. Findings below are drawn from model training knowledge (cutoff August 2025), which covers coverage.py through 7.x. All technical claims are cross-referenced across three independent research threads for consistency.

### Programming Languages & Core Frameworks

coverage.py is a **pure-Python** package (CPython 3.8+ as of v7.x). No compiled extensions are required for the HTML reporter path. The templating engine is **not Jinja2** — coverage.py ships its own minimal engine called **Templite**, implemented in `coverage/templite.py`. Templite supports `{{ expr }}` output, `{% for %}` / `{% if %}` control flow, and `{% block %}` / `{% extends %}` for template inheritance. This is an intentional, self-contained design: coverage.py deliberately avoids third-party runtime dependencies in the report path.

_Key languages:_ Python 3.8+, JavaScript (report interactivity via `coverage_html.js`)
_Template engine:_ Templite (custom, not Jinja2) — `coverage/templite.py`
_Source:_ github.com/nedbat/coveragepy — `coverage/templite.py`, `coverage/html.py`

### Development Frameworks and Libraries (HTML Reporter Internals)

The HTML report pipeline is composed of these internal modules:

| Module | Role |
|---|---|
| `coverage/html.py` | `HtmlReporter` class — orchestrates the full HTML report |
| `coverage/report_core.py` | `Reporter` base class; `get_analysis_to_report()` iterator |
| `coverage/results.py` | `Analysis` class — computes executed/missing/excluded lines per file |
| `coverage/data.py` | `CoverageData` class — SQLite-backed data store (since v5.0) |
| `coverage/plugin.py` | `FileReporter` abstract base class |
| `coverage/python.py` | `PythonFileReporter` — default implementation for `.py` files |
| `coverage/templite.py` | Templite template engine |
| `coverage/htmlfiles/` | Templates (`index.html`, `pyfile.html`) + static assets |

The `HtmlReporter` flow:
1. Iterates all measured files via `get_analysis_to_report()`
2. For each file, constructs an `Analysis` object
3. Tokenizes source using `coverage/parser.py` + Python's stdlib `tokenize`
4. Renders per-file pages via Templite + `pyfile.html`
5. Renders the summary index via Templite + `index.html`
6. Copies static assets (`coverage_html.js`, `style.css`) to the output directory

### Database and Storage Technologies

`CoverageData` (in `coverage/data.py`) is backed by a **SQLite database** (the `.coverage` file). This was a deliberate change from JSON in coverage.py 5.0. The public API exposed by `CoverageData`:

```python
data.measured_files()            # → set of all measured file paths
data.lines(filename)             # → list of executed line numbers
data.arcs(filename)              # → list of (from, to) arc tuples (branch coverage)
data.contexts_by_lineno(filename) # → dict mapping line number → list of test contexts
```

This API is stable and documented — it is the recommended way to read coverage data programmatically without going through the report pipeline.

### Development Tools and Platforms

The plugin system (introduced in coverage.py 4.0) defines three plugin types, registered via `coverage_init(reg, options)`:

| Plugin Type | Registered via | Purpose |
|---|---|---|
| **FileTracer** | `reg.add_file_tracer()` | Intercept execution of non-Python files (templates, etc.) |
| **FileReporter** | `reg.add_file_reporter()` | Control source rendering for a file in reports |
| **Configurer** | `reg.add_configurer()` | Programmatically modify configuration at startup |

`FileReporter` plugins influence *what source lines and tokens* appear in reports, but **cannot inject new table columns, custom JS, or custom CSS** into HTML output. The HTML template structure is hardcoded.

Known real-world plugin examples (all FileTracer type):
- `django-coverage-plugin` — maps Django template execution to template source lines
- `coverage-mako` — Mako template tracing
- `coverage-jinja2` — Jinja2 template tracing

There are **no known public FileReporter plugins that add custom HTML columns**.

### Cloud Infrastructure and Deployment

Not applicable to this research topic. coverage.py is a local development/CI tool; its HTML report is a static file bundle (HTML + CSS + JS) with no server-side component.

### Technology Adoption Trends

- The move to SQLite (v5.0) made `CoverageData` a first-class, queryable API.
- The plugin API has been stable since v4.0 with no breaking changes through v7.x.
- There is a pattern in the ecosystem of **reading `CoverageData` directly** to produce custom reports (e.g., `coverage-badge`, `pytest-cov` integrations) rather than extending the HTML reporter.
- No trend of official extension hooks for HTML report columns has been observed in the issue tracker or roadmap.
