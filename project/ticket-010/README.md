# Ticket 010: Reject incomplete pytest scans

- **Status**: IN_PROGRESS
- **Workflow state**: PUBLICATION
- **Owner**: agent:codex
- **Queue request**: PLF-010, parent paxlet-com/willmux:PLF-17161

SESSION_EXECUTION_AUTHORIZATION: continue the qualified collector repair, test and submit through independent protected publication. Source writing was admitted by the protected controller after exact owner approval. The qualified source is ready for independently verified publication.

Own only the two collector/CLI source files, tests/test_pytest_outcomes.py and this ticket carrier, bound in intent.json. The isolated proposal passes 23 focused regressions and 75 full tests on each locked Python3.11/3.13 environment. Required hosted matrix and independent Validator remain unchanged.

- [x] AC-01: Propagate failed child exits and reject stale/missing/partial outcome or coverage evidence.
- [x] AC-02: Apply under fenced lease; preserve previously complete scan on failure and pass owning tests.
- [ ] AC-03: Current-base exact-head protected checks and independent publication.

## Validation

Exact proposal applied after owner-approved protected controller admission (fence8). Full locked test suites: Python3.11.13/pytest9.0.3 — 75 passed; Python3.13.12/pytest9.0.3 — 75 passed. Ruff and Git whitespace checks pass. Immutable docs checker ebe7501063ef4f3e63ded610c2d3183010ca636e passes with an existing review-due warning for internal-dependencies.md. Protected hosted matrix and independent Validator remain required for AC-03.

Independent review requested a revision of the skipped-outcome fixture. Fresh admission fence9 owns this correction. The real subprocess test observes PASS; a controlled fresh JUnit report independently exercises skipped metadata without disabling any test. All negative child/report guards remain. Full locked suites on Python3.11 and3.13 now pass76tests each; Ruff and whitespace checks pass. AC-03 still waits for fresh exact-head protected review.

PR12 independently merged the child/outcome repair, but advisory review identified an output-publication failure gap in AC-02. Continue the same accepted source scope: publish one complete coverage/outcome artifact and add publication-failure regressions. Existing protected checks and runtime installation remain separate.

Atomic publication follow-up under fresh fence10: coverage.json is the sole canonical artifact and contains coverage, testless.scan/v1 outcomes, a fresh observation ID and the validated JUnit hash. Only one atomic replace publishes it; publication failure preserves the previous complete artifact and yields a CLI error. Three focused regressions fail on published v2 and pass candidate (the CLI assertion explicitly checks its error prefix). Full locked suites pass79tests on Python3.11 and3.13; the strengthened focused cases also pass. PR12 terminal review/merge evidence is preserved. Fresh follow-up PR and independent gates remain required to finish AC-03.
