# ticket-005: Fix coverage contexts loading, scan runner, and pytest configuration

- **Status**: IN_PROGRESS
- **Workflow state**: EDIT

SESSION_EXECUTION_AUTHORIZATION: On 2026-09-27 the user requested investigating whether
`testless` is functioning correctly, repairing any defects, and evaluating its ability
to reduce unnecessary tests across projects.

AC-01: `load_coverage_json` supports both standard `coverage.py 7.x` format (`{line: [contexts]}`)
and inverted/legacy mock format (`{context: [lines]}`), parsing line-to-test mappings accurately.
AC-02: `run_pytest` checks if `pytest_jsonreport` is installed before passing `--json-report`,
preventing crashes on standard pytest installations, and ensures `coverage json --show-contexts`
is produced.
AC-03: `pyproject.toml` includes `pythonpath = ["src"]` under `[tool.pytest.ini_options]` so that
pytest discovers the `testless` package without requiring manual `PYTHONPATH` exports.
AC-04: Unit tests verify both coverage JSON formats and resilient test collection.
AC-05: All tests pass with zero regressions.
