"""Tests for duplicate_tests analyzer."""

from __future__ import annotations

from testless.analyze.duplicate_tests import _duplicate_score, find_duplicates
from testless.collect.fixture_index import FixtureIndex
from testless.models.coverage_map import CoverageMap, FileCoverage
from testless.models.findings import TestMeta


def _make_tests(*node_ids: str) -> list[TestMeta]:
    return [
        TestMeta(node_id=nid, file=nid.split("::")[0], name=nid.split("::")[-1])
        for nid in node_ids
    ]


def test_duplicate_score_formula():
    score = _duplicate_score(1.0, 1.0, 1.0, 1.0)
    assert abs(score - 1.0) < 1e-9

    score = _duplicate_score(0.0, 0.0, 0.0, 0.0)
    assert score == 0.0


def test_no_duplicates_disjoint_coverage():
    fc = FileCoverage(path="src/app.py", line_to_tests={1: ["tests/a.py::test_a"], 2: ["tests/a.py::test_b"]})
    cmap = CoverageMap(files={"src/app.py": fc})
    tests = _make_tests("tests/a.py::test_a", "tests/a.py::test_b")
    result = find_duplicates(tests, cmap, FixtureIndex(), min_score=0.85)
    assert result == []


def test_finds_duplicate_identical_coverage():
    fc = FileCoverage(
        path="src/app.py",
        line_to_tests={1: ["tests/a.py::test_a", "tests/a.py::test_b"], 2: ["tests/a.py::test_a", "tests/a.py::test_b"]},
    )
    cmap = CoverageMap(files={"src/app.py": fc})
    tests = _make_tests("tests/a.py::test_a", "tests/a.py::test_b")
    result = find_duplicates(tests, cmap, FixtureIndex(), min_score=0.45)
    # coverage overlap alone should push score above 0.45
    assert len(result) >= 1
    assert result[0].coverage_overlap == 1.0


def test_result_sorted_by_score_descending():
    fc = FileCoverage(
        path="src/app.py",
        line_to_tests={
            1: ["t::a", "t::b"],
            2: ["t::a", "t::b"],
            3: ["t::c", "t::d"],
            4: ["t::c", "t::d"],
        },
    )
    cmap = CoverageMap(files={"src/app.py": fc})
    tests = _make_tests("t::a", "t::b", "t::c", "t::d")
    result = find_duplicates(tests, cmap, FixtureIndex(), min_score=0.0)
    scores = [r.score for r in result]
    assert scores == sorted(scores, reverse=True)
