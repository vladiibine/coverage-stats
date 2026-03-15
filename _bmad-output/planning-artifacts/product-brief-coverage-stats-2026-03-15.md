---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments:
  - _bmad-output/planning-artifacts/research/technical-coverage-py-html-reporting-extensibility-research-2026-03-15.md
  - _bmad-output/planning-artifacts/research/technical-coverage-profiler-research-2026-03-15.md
  - _bmad-output/planning-artifacts/research/technical-enhancing-coverage-py-research-2026-03-15.md
date: '2026-03-15'
author: Vlad
---

# Product Brief: coverage-stats

<!-- Content will be appended sequentially through collaborative workflow steps -->

## Executive Summary

**coverage-stats** is a standalone Python test analytics tool that replaces the binary "executed/not executed" metric of traditional coverage tools with a richer, intent-aware model. By allowing developers to explicitly declare which tests are responsible for which code units — and by independently tracking execution counts and assert density across both deliberate and incidental paths — coverage-stats gives developers, QA managers, architects, and CTOs an honest, actionable picture of test quality.

The tool ships a custom `sys.settrace`-based profiler (no dependency on coverage.py), a `@covers` decorator API, and multiple output formats: HTML reports (index + per-file views, similar to coverage.py's UI), JSON, and CSV. It is designed to run as a drop-in pytest plugin.

---

## Core Vision

### Problem Statement

Code coverage tools today answer only one question: *was this line executed during the test suite?* This binary signal is widely acknowledged as a weak metric — a line can appear "covered" simply because an unrelated test happened to pass through it. There is no way to distinguish between a line that is **deliberately tested** (a test author explicitly declared they are verifying this code) and a line that is **incidentally executed** (it ran as a side effect of something else being tested). Worse, there is no way to understand the *assertion pressure* on a line — how much actual verification is backing its execution.

### Problem Impact

- Developers get false confidence: 80% coverage may mean 80% of lines were touched, but most of those touches may be incidental with zero assertions targeting that code.
- Architects and CTOs cannot identify areas of the codebase that lack *deliberate* testing — the parts that truly matter for correctness guarantees.
- QA managers have no metric to drive *quality of coverage*, only quantity.
- Teams making refactoring or risk decisions rely on coverage numbers that systematically overstate test strength.

### Why Existing Solutions Fall Short

**coverage.py** is the standard, but it only tracks binary line execution. It has no concept of intent, no assert counting, and no way to distinguish who caused a line to run. Its plugin API cannot add new data dimensions to its HTML report columns. Building on top of it would require coupling to its internals.

No existing open-source tool combines: explicit test-to-code ownership declaration + incidental vs. deliberate execution counting + assert density measurement + independent profiling + coverage.py-style HTML reporting.

### Proposed Solution

**coverage-stats** introduces four new metrics tracked at the line level:

| Metric                        | Definition                                                                 |
|-------------------------------|----------------------------------------------------------------------------|
| **Incidental executions**     | Times this line ran, but no test explicitly claimed ownership of it        |
| **Deliberate executions**    | Times this line ran, triggered by a test that declared it covers this code |
| **Incidental assert density** | Asserts fired by incidental tests ÷ total lines in file                    |
| **Deliberate assert density** | Asserts fired by deliberate tests ÷ total lines in file                    |

Developers mark ownership with a decorator:
```python
@covers(MyClass.my_method, 'module.OtherClass.method')
def test_something():
    ...
```

The tool implements its own `sys.settrace` profiler, collects data during a pytest run, and produces:
- An **HTML report** (collapsible file index per folder + per-file line-level view) mirroring coverage.py's UX
- **JSON** and **CSV** exports for CI integration and dashboarding

### Key Differentiators

- **Intent-aware profiling**: The only tool that distinguishes *why* a line was executed, not just *that* it was
- **Assert density as a signal**: Quantifies how much verification pressure backs each line — a metric no existing tool exposes
- **Hard error on bad references**: `@covers` resolves targets at collection time; unresolvable references fail loudly, preventing silently misleading annotations
- **Fully independent implementation**: No dependency on coverage.py — custom profiler, custom reporter, fully owned data model
- **"Coverage is broken — here's what better looks like"**: Directly addresses the widely-held frustration with traditional coverage metrics with a concrete, superior alternative

---

## Target Users

### Primary Users

**Persona: "The Conscientious Developer" — Alex**

Alex is a mid-to-senior software engineer working on a Python backend — either a maturing codebase with years of accumulated tests, or a greenfield project where they want to build good habits from day one. Alex cares about code quality and is skeptical of coverage as a metric — they've seen 70% coverage numbers that meant very little, and they've been burned by regressions in "covered" code.

**Core pain point:** When Alex looks at a file with 70% coverage, they have no idea whether that 70% reflects real verification or just incidental execution. They can't tell whether the logic in that file is *actually tested* or just happens to run when other things are tested. They want confidence that their test suite would catch bugs in the code they care about most — and right now they have no way to build that confidence systematically.

**How they adopt coverage-stats:** Alex adopts it incrementally. They install it as a pytest plugin, run it once to see the baseline (likely: lots of incidental coverage, low deliberate coverage, low assert density), and then begin adding `@covers` decorators to their most important tests. Over time, they work through the codebase test-by-test. There's a cost — annotating tests takes effort — but Alex accepts this trade-off because the payoff is a meaningful signal.

**Success moment:** When Alex adds `@covers` to a focused test suite for a critical module and sees the deliberate assert density climb, they know that module is genuinely protected. When they later refactor it and the tests catch a bug, they have evidence the tool paid off.

**What they need from the tool:**
- Easy pytest integration (minimal setup friction)
- Clear, line-level HTML report they can open locally or review in CI artifacts
- Hard errors on bad `@covers` references — no silent mistakes
- Incremental adoption: the tool is useful even before all tests are annotated

---

### Secondary Users

**Persona: "The Quality Steward" — Maria (QA Manager / Engineering Manager)**

Maria oversees test quality across one or more teams. She doesn't run the test suite herself day-to-day — she reviews HTML reports generated by CI pipelines. Her concern is not individual lines of code but patterns: are the critical modules of the application intentionally tested? Is the assert density on payment processing, auth, or data migration code high enough to trust a release?

**How they use coverage-stats:** Maria reviews the HTML index report after each sprint or before a release. The folder-collapsible view lets her get a bird's-eye view of intentional coverage % and deliberate assert density across subsystems. She uses this to direct the team's testing investment — "we're shipping a refactor to the billing module next week and deliberate coverage is at 12% — let's fix that first."

---

**Persona: "The Risk Assessor" — David (Architect / CTO)**

David thinks in systems and risk. Before a major release or architectural change, he wants to know: which parts of the codebase are genuinely well-tested vs. superficially covered? He consumes summary-level HTML reports and potentially JSON exports fed into dashboards. His question is: "Can I trust this release?" and "Where should the team invest testing effort to reduce risk?"

**What they need from the tool:**
- HTML reports accessible as CI artifacts, no local tool setup required
- Folder-level aggregated stats to reason about subsystems, not just individual files
- JSON/CSV exports for integration into dashboards or release-readiness checklists

---

### User Journey

**Alex (Primary — Developer):**
1. **Discovery:** Finds coverage-stats via PyPI, GitHub, or a blog post about "coverage is a broken metric"
2. **Onboarding:** `pip install coverage-stats`, adds pytest plugin config, runs first report — sees the baseline state (high incidental, low deliberate)
3. **Core usage:** Adds `@covers` decorators to key tests incrementally; re-runs after each sprint to track progress
4. **Aha moment:** Opens the per-file HTML view and sees a critical module go from 0% deliberate coverage to 60% — and understands for the first time which lines are *actually* verified
5. **Long-term:** `@covers` becomes a team norm; coverage-stats runs in CI; deliberate coverage % becomes a meaningful team health metric

**Maria / David (Secondary — Managers/Architects):**
1. **Discovery:** Introduced to the tool by a developer (Alex) or sees the CI report linked in a PR or release checklist
2. **Onboarding:** Zero — they only consume HTML artifacts or JSON outputs
3. **Core usage:** Review index report pre-release or in sprint reviews; use folder-level view to identify risk areas
4. **Aha moment:** Sees a module with high traditional coverage but near-zero deliberate coverage and assert density — and realises the team has been flying blind on that code
5. **Long-term:** Incorporates deliberate coverage thresholds into release-readiness criteria; drives testing investment decisions based on assert density trends

---

## Success Metrics

### User Success Metrics

**The core signal of user success is behavioral change over time:**

- **Deliberate assert density increases on complex/critical modules** — the primary health indicator that the tool is being used meaningfully. As developers add `@covers` annotations to tests targeting important code, the deliberate assert density on those modules climbs. This is the metric that indicates the tool is doing its job.

- **Deliberate coverage expands into previously uncovered critical code** — areas the team considers important that had zero deliberate coverage begin to acquire it. This reflects a shift from accidental to intentional testing.

- **Discovery of coverage illusion** — the aha moment when a developer first annotates tests and sees that a module with high incidental coverage has near-zero deliberate coverage. This is when the value of the tool becomes undeniable. It often reveals that the same code paths are being exercised repeatedly by unrelated tests, providing no additional confidence.

- **Continued CI integration** — the tool running consistently in CI pipelines is the retention signal. A team that keeps it in CI has accepted it as part of their quality workflow.

**Minimum viable value threshold:** The tool becomes meaningful as soon as any tests are annotated for a given module. Even partial annotation immediately exposes the deliberate vs. incidental split and triggers the insight moment.

### Business Objectives

As an open-source project, business success is defined by adoption, community trust, and ecosystem fit:

- **PyPI presence and discoverability** — published, installable, and findable by Python developers searching for test quality tooling
- **Community adoption** — developers choosing to integrate coverage-stats into their projects and CI pipelines
- **Mindshare** — becoming part of the conversation around "coverage is a broken metric" and offering a concrete, credible alternative
- **No commercial angle** — success is measured purely in community impact, not revenue

### Key Performance Indicators

| KPI | What it measures | Why it matters |
|---|---|---|
| PyPI monthly downloads | Adoption rate and growth | Primary signal that the tool is being discovered and used |
| GitHub stars | Community interest and perceived value | Proxy for developer trust and recommendation |
| GitHub issues / PRs from community | Ecosystem engagement | Indicates the tool is used seriously enough to warrant contribution |
| Deliberate coverage % growth (per-project) | In-tool user behavior | Leading indicator that users are actively annotating, not just installing |
| Deliberate assert density trend (per-project) | Quality of test investment over time | The metric that most directly reflects the tool's intended impact |

The last two KPIs are measured within individual users' projects (visible in their reports), not centrally — but they represent the real value the tool is creating at the coalface.

---

## MVP Scope

### Core Features

**1. Custom `sys.settrace` Profiler**
A fully independent line-level execution tracer with no dependency on coverage.py. Tracks which lines execute during each test, which test is currently running, and how many assertions the test fires. Maintains the deliberate/incidental distinction based on `@covers` annotations.

**2. `@covers` Decorator**
A pytest-integrated decorator that declares explicit ownership of code units. Accepts Python objects, dotted string references, or lists of either. References are resolved just before the test runs — if any reference cannot be resolved at that moment, an exception is raised and the test fails. The suite continues; bad references surface as individual test failures, not collection-phase errors. No silent failures.

```python
@covers(MyClass.my_method, 'mymodule.OtherClass.other_method')
def test_something():
    ...
```

**3. Four Core Metrics (tracked per line)**

| Metric | Definition |
|---|---|
| Incidental executions | Line ran during a test that did not claim ownership of it |
| Deliberate executions | Line ran during a test that explicitly declared it covers this code |
| Incidental assert density | Asserts from incidental tests ÷ total lines in file |
| Deliberate assert density | Asserts from deliberate tests ÷ total lines in file |

**4. HTML Report — Index Page**
A coverage.py-style summary index listing all measured files and folders with:
- Incidental coverage % per file/folder
- Deliberate coverage % per file/folder
- Incidental assert density per file/folder
- Deliberate assert density per file/folder

Files are grouped by folder with expand/collapse support. Folder rows show aggregated stats across all files within them.

**5. HTML Report — Per-File View**
A line-level breakdown for each source file, showing per-line incidental and deliberate execution counts and assert contributions — mirroring coverage.py's per-file view UX.

**6. JSON and CSV Export**
Machine-readable output of all collected metrics for CI integration, dashboarding, or threshold enforcement by downstream tooling.

**7. pytest Plugin Integration**
Distributed as a pytest plugin. Minimal setup — configure via `pytest.ini` / `pyproject.toml`, run with `pytest --coverage-stats`.

---

### Out of Scope for MVP

- **Historical trend tracking** — comparing metrics across runs over time; users can implement this externally using the JSON/CSV exports
- **IDE / editor integration** — no VS Code extension or inline annotations in MVP
- **Non-pytest test runners** — unittest, nose, and others are not supported in v1
- **Branch-level coverage** — line-level granularity only; branch arc tracking is a future concern
- **Hosted report viewer or dashboard** — the tool produces static HTML artifacts; no server component

---

### MVP Success Criteria

- A developer can `pip install coverage-stats`, configure it as a pytest plugin, annotate at least one test with `@covers`, and immediately see the deliberate vs. incidental split in the HTML report
- The HTML report index renders folder-level aggregated stats with expand/collapse and per-file drill-down
- JSON and CSV exports contain the complete metric set and are usable in CI pipelines without additional tooling
- Bad `@covers` references raise clear, actionable exceptions just before the affected test runs — the test fails, the suite continues, nothing is silently ignored
- The tool runs independently with zero coverage.py dependency

---

### Future Vision

- **Historical trend views** — track deliberate coverage % and assert density trends over time across runs, surfaced in the HTML report
- **Cross-run comparison** — diff two reports to highlight regressions or improvements in deliberate coverage
- **Support for additional test runners** — unittest, Hypothesis, and other Python test frameworks
- **Branch-level deliberate coverage** — extend the profiler to track branch arcs, distinguishing deliberate vs. incidental branch coverage
- **IDE integration** — inline annotations in VS Code or PyCharm showing per-line deliberate/incidental stats
- **README badges** — auto-generated shields.io-style badges for deliberate coverage % and assert density
- **Deeper folder analytics** — drill-down views with per-subfolder breakdown and treemap visualisations of coverage distribution across the project
