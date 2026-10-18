# testless


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.1.9-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$0.61-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-7.0h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $0.6101 (11 commits)
- 👤 **Human dev:** ~$700 (7.0h @ $100/h, 30min dedup)

Generated on 2026-07-06 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---

**testless** is a Python package that sits as an analytical layer on top of your existing test suite.
It analyses test **value**, **coverage overlap**, **duplication**, and **missing gaps**, then generates
LLM-ready **planfile** tickets that describe exactly what to remove, refactor, or add.

---

## Features

| Command | What it does |
|---------|--------------|
| `testless scan` | Run pytest with `--cov-context=test` and collect metadata |
| `testless duplicates` | Detect duplicate tests (coverage + AST + fixture overlap) |
| `testless missing` | Suggest smoke, e2e, contract, and TestQL tests |
| `testless planfiles` | Generate YAML planfile tickets for an LLM |
| `testless doctor` | Answer questions: "what to remove?", "what to add?" |

---

## Quick Start

```bash
pip install testless
# or with uv:
uv add --dev testless

# 1. Scan your project
testless scan

# 2. Find duplicate tests (threshold: 85 % similarity)
testless duplicates --min-overlap 0.85

# 3. Find missing smoke / service / e2e tests
testless missing --services src/myapp

# 4. Generate LLM planfiles
testless planfiles --out .planfiles/ --with-prompts

# 5. Ask doctor questions
testless doctor "which tests should I remove?"
```

---

## Configuration

Create a `.testless.yml` in your project root:

```yaml
packages:
  - myapp

test_dirs:
  - tests

min_duplicate_score: 0.85
planfiles_dir: .planfiles
coverage_dir: .coverage_data

pytest_args:
  - --tb=short
```

---

## Planfile format

Each generated ticket is a self-contained YAML file that an LLM can act on:

```yaml
version: "1"
kind: duplicate
id: "DUP-3A7F2C"
title: "Remove duplicate test: test_health_ok vs test_health_status_200"
goal: "Reduce test suite redundancy without losing unique coverage"
context:
  test_a: tests/api/test_health.py::test_health_ok
  test_b: tests/api/test_health.py::test_health_status_200
evidence:
  - description: "score=0.93, coverage_overlap=0.95"
    score: 0.93
impact:
  risk: low
  expected_gains:
    - shorter test run time
    - reduced maintenance burden
tasks:
  - description: Compare test_health_ok and test_health_status_200 manually
  - description: Remove the weaker/less descriptive test
  - description: Run suite and verify no coverage regression
acceptance_criteria:
  - No decrease in unique line coverage
  - All remaining tests pass
llm_hints:
  style: minimal change
  safe_refactor: true
```

---

## Architecture

```
src/testless/
├── cli.py                  # Click CLI
├── config.py               # .testless.yml loader
├── models/
│   ├── planfile.py         # Pydantic Planfile model
│   ├── findings.py         # Finding models
│   └── coverage_map.py     # CoverageMap model
├── collect/
│   ├── pytest_runner.py    # Run pytest, collect metadata
│   ├── coverage_loader.py  # Parse coverage.json contexts
│   ├── fixture_index.py    # AST-based fixture indexer
│   └── endpoint_inventory.py  # HTTP endpoint/service scanner
├── analyze/
│   ├── duplicate_tests.py  # Duplicate detection
│   ├── dead_tests.py       # Dead test detection
│   ├── missing_tests.py    # Missing test suggestions
│   ├── service_risk.py     # Service risk scoring
│   └── refactor_candidates.py  # Refactor detection
├── suggest/
│   ├── smoke.py            # Smoke test templates
│   ├── e2e.py              # E2E test templates
│   ├── service_tests.py    # Service contract templates
│   └── testql.py           # TestQL stub generator
├── tickets/
│   ├── builder.py          # Build Planfile from findings
│   ├── serializer.py       # Write planfiles to disk
│   └── prompts.py          # Attach LLM prompts
└── reporters/
    ├── console.py          # Coloured terminal output
    ├── markdown.py         # Markdown report
    └── json.py             # JSON report
```

---

## License

Licensed under Apache-2.0.
