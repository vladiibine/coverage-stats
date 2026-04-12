from __future__ import annotations

import nox  # noqa

nox.options.default_venv_backend = "uv"

PYTHON_VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"]


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    """Run the unit and integration test suite."""
    session.install("-e", ".[dev]")
    session.run(
        "pytest", "tests/",
        "--ignore=tests/benchmarks",
        "--coverage-stats",
        "--coverage-stats-format", "html",
        "--coverage-stats-output", f"coverage-stats-report/{session.python}",
        *session.posargs,
    )


@nox.session
def mypy(session: nox.Session) -> None:
    """Type-check with mypy."""
    session.install(".[dev]")
    session.run("mypy", "src/", "scripts/")


@nox.session
def lint(session: nox.Session) -> None:
    """Lint with ruff."""
    session.install("ruff")
    session.run("ruff", "check", "src/", "tests/", "scripts/")


@nox.session
def imports(session: nox.Session) -> None:
    """Check import layering with import-linter."""
    session.install(".[dev]")
    session.run("lint-imports")


@nox.session
def benchmark(session: nox.Session) -> None:
    """Run performance benchmarks (not part of the default suite).

    Results are printed to stdout.  Pass --benchmark-save=<name> to persist
    a baseline and --benchmark-compare to compare against a saved run:

        nox -s benchmark -- --benchmark-save=baseline
        nox -s benchmark -- --benchmark-compare=baseline
    """
    session.install("-e", ".[dev,benchmark]")
    session.run(
        "pytest", "tests/benchmarks/",
        "--benchmark-only",
        "--benchmark-sort=mean",
        "--benchmark-columns=min,mean,stddev,rounds,iterations",
        *session.posargs,
    )
