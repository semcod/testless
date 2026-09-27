"""Tests for coverage_loader."""

from __future__ import annotations

import json
from pathlib import Path

from testless.collect.coverage_loader import load_coverage_json
from testless.models.coverage_map import CoverageMap


def _write_coverage_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_missing_file(tmp_path: Path):
    result = load_coverage_json(tmp_path / "nonexistent.json")
    assert isinstance(result, CoverageMap)
    assert result.files == {}


def test_load_basic_coverage(tmp_path: Path):
    coverage_data = {
        "files": {
            "src/app.py": {
                "contexts": {
                    "tests/test_app.py::test_hello|run": [1, 2, 3],
                    "tests/test_app.py::test_world|run": [3, 4],
                }
            }
        }
    }
    p = tmp_path / "coverage.json"
    _write_coverage_json(p, coverage_data)

    cmap = load_coverage_json(p)
    assert "src/app.py" in cmap.files
    fc = cmap.files["src/app.py"]

    # Line 1 and 2 should be covered by test_hello
    assert "tests/test_app.py::test_hello" in fc.line_to_tests[1]
    assert "tests/test_app.py::test_hello" in fc.line_to_tests[2]

    # Line 3 covered by both
    assert "tests/test_app.py::test_hello" in fc.line_to_tests[3]
    assert "tests/test_app.py::test_world" in fc.line_to_tests[3]

    # Line 4 covered only by test_world
    assert "tests/test_app.py::test_world" in fc.line_to_tests[4]
    assert "tests/test_app.py::test_hello" not in fc.line_to_tests.get(4, [])


def test_load_strips_phase_suffix(tmp_path: Path):
    coverage_data = {
        "files": {
            "src/x.py": {
                "contexts": {
                    "tests/test_x.py::test_a|setup": [10],
                    "tests/test_x.py::test_a|teardown": [10],
                    "tests/test_x.py::test_a|run": [10, 11],
                }
            }
        }
    }
    p = tmp_path / "cov.json"
    _write_coverage_json(p, coverage_data)

    cmap = load_coverage_json(p)
    fc = cmap.files["src/x.py"]
    # All phases should map to the same node_id
    assert fc.line_to_tests[10] == ["tests/test_x.py::test_a"]
    assert fc.line_to_tests[11] == ["tests/test_x.py::test_a"]


def test_load_coverage_7x_format(tmp_path: Path):
    """Verify loading real coverage.py 7.x schema with line number keys."""
    coverage_data = {
        "files": {
            "src/service.py": {
                "contexts": {
                    "10": ["test|tests/test_service.py::test_alpha|run"],
                    "20": [
                        "test|tests/test_service.py::test_alpha|run",
                        "test|tests/test_service.py::test_beta|run",
                    ],
                    "30": ["test|tests/test_service.py::test_beta|run"],
                    "40": ["test"],  # should be ignored
                }
            }
        }
    }
    p = tmp_path / "cov7.json"
    _write_coverage_json(p, coverage_data)

    cmap = load_coverage_json(p)
    assert "src/service.py" in cmap.files
    fc = cmap.files["src/service.py"]

    assert fc.line_to_tests[10] == ["tests/test_service.py::test_alpha"]
    assert "tests/test_service.py::test_alpha" in fc.line_to_tests[20]
    assert "tests/test_service.py::test_beta" in fc.line_to_tests[20]
    assert fc.line_to_tests[30] == ["tests/test_service.py::test_beta"]
    assert 40 not in fc.line_to_tests

