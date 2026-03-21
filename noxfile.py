from __future__ import annotations

import nox  # noqa

nox.options.default_venv_backend = "uv"

PYTHON_VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"]


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    """Run the unit and integration test suite."""
    session.install(".")
    session.install("pytest")
    session.run("pytest", "tests/", *session.posargs)


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
