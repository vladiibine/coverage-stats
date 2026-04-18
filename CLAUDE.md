# Claude Instructions

- Never run `git push` for any reason.
- Use red-green TDD when writing code
- For running individual tests, use the venvs already created by nox in ./.nox/tests-<python-version>. For running the entire test suite, use `nox -s tests` (to run on all python versions) or `nox -s tests-<python-version>` for specific python versions (from 3.9 to 3.14)
