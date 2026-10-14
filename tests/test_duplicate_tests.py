"""Tests for duplicate_tests analyzer."""

from __future__ import annotations

import ast
import difflib

from testless.analyze.duplicate_tests import _ast_similarity, _duplicate_score, find_duplicates
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


def test_source_parsed_once_and_refreshed_on_next_analysis(tmp_path, monkeypatch):
    file = tmp_path / "test_examples.py"
    file.write_text("\n".join(f"def test_{i}():\n    return {i}" for i in range(6)))
    ids = [f"{file}::test_{i}" for i in range(6)]
    tests = _make_tests(*ids)
    cmap = CoverageMap(files={"source.py": FileCoverage(path="source.py", line_to_tests={1: ids})})
    calls = []
    original = ast.parse

    def parse(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(ast, "parse", parse)
    first = find_duplicates(tests, cmap, FixtureIndex(), min_score=0)
    assert len(first) == 15
    assert len(calls) == 1
    file.write_text("\n".join(f"def test_{i}():\n    return 'different body {i}'" for i in range(6)))
    second = find_duplicates(tests, cmap, FixtureIndex(), min_score=0)
    assert len(calls) == 2
    assert second != first


def test_cached_scores_match_pairwise_components_with_duplicate_node_ids(tmp_path):
    file = tmp_path / "test_examples.py"
    file.write_text("def test_a():\n    return 1\n\ndef test_b():\n    return 2\n")
    ids = [f"{file}::test_a", f"{file}::test_b", f"{file}::test_missing[param]"]
    tests = _make_tests(*ids, ids[0])
    cmap = CoverageMap(files={
        "a.py": FileCoverage(path="a.py", line_to_tests={1: ids[:2], 2: ids[1:]}),
        "b.py": FileCoverage(path="b.py", line_to_tests={1: [ids[0]]}),
    })
    fixtures = FixtureIndex()
    fixtures.scan_directory(tmp_path)
    expected = []
    seen = set()
    for i, a in enumerate(tests):
        for b in tests[i + 1:]:
            pair = frozenset({a.node_id, b.node_id})
            if pair in seen:
                continue
            seen.add(pair)
            overlap = cmap.overlap(a.node_id, b.node_id)
            fix = fixtures.fixture_overlap(a.node_id, b.node_id)
            similarity = _ast_similarity(a.file, a.name, b.file, b.name)
            names = difflib.SequenceMatcher(None, a.name, b.name).ratio()
            expected.append((a.node_id, b.node_id,
                             round(_duplicate_score(overlap, similarity, fix, names), 3),
                             round(overlap, 3), round(similarity, 3), round(fix, 3), round(names, 3)))
    expected.sort(key=lambda row: row[2], reverse=True)
    actual = find_duplicates(tests, cmap, fixtures, min_score=0)
    assert [(f.test_a, f.test_b, f.score, f.coverage_overlap, f.ast_similarity,
             f.fixture_overlap, f.name_similarity) for f in actual] == expected


def test_upper_bound_keeps_inclusive_threshold_and_skips_impossible_sources(tmp_path, monkeypatch):
    missing = tmp_path / "missing.py"
    ids = [f"{missing}::test_a", f"{missing}::test_b"]
    tests = _make_tests(*ids)
    cmap = CoverageMap(files={"a.py": FileCoverage(path="a.py", line_to_tests={1: ids})})
    pair = find_duplicates(tests, cmap, FixtureIndex(), min_score=0)[0]
    # Use the exact unrounded score because reporting rounds after filtering.
    threshold = _duplicate_score(1, 0, 0, difflib.SequenceMatcher(None, "test_a", "test_b").ratio())
    assert find_duplicates(tests, cmap, FixtureIndex(), min_score=threshold) == [pair]
    missing.write_text("def test_a():\n    return 1\n\ndef test_b():\n    return 2\n")
    monkeypatch.setattr(ast, "parse", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("not needed")))
    assert find_duplicates(tests, CoverageMap(), FixtureIndex(), min_score=0.85) == []
