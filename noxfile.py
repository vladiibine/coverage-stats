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
        "--coverage-stats",
        "--coverage-stats-format", "html",
        "--coverage-stats-output", f"coverage-stats-report/{session.python}",
        *session.posargs,
    )


@nox.session
def mypy(session: nox.Session) -> None:
    """Type-check with mypy."""
    session.install(".[dev]")
    session.run("mypy", "src/")


@nox.session
def lint(session: nox.Session) -> None:
    """Lint with ruff."""
    session.install("ruff")
    session.run("ruff", "check", "src/", "tests/")


@nox.session
def import_lint(session: nox.Session) -> None:
    """Check import layering with import-linter."""
    session.install(".[dev]")
    session.run("lint-imports")
