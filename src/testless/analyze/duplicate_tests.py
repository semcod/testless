"""Detect duplicate tests using coverage overlap, AST similarity, fixtures and names."""

from __future__ import annotations

import ast
import difflib
from pathlib import Path

from testless.collect.fixture_index import FixtureIndex
from testless.models.coverage_map import CoverageMap
from testless.models.findings import DuplicateFinding, TestMeta


def _ast_similarity(file_a: str, name_a: str, file_b: str, name_b: str) -> float:
    """Compute normalized edit-distance similarity between two test function bodies."""

    def _get_source(file: str, name: str) -> str:
        path = Path(file)
        if not path.exists():
            return ""
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
                return ast.unparse(node)
        return ""

    src_a = _get_source(file_a, name_a)
    src_b = _get_source(file_b, name_b)
    if not src_a or not src_b:
        return 0.0
    return difflib.SequenceMatcher(None, src_a, src_b).ratio()


def _name_similarity(name_a: str, name_b: str) -> float:
    """Normalized edit-distance similarity between two test names."""
    return difflib.SequenceMatcher(None, name_a, name_b).ratio()


def _duplicate_score(
    cov_overlap: float,
    ast_sim: float,
    fix_overlap: float,
    name_sim: float,
) -> float:
    return (
        0.45 * cov_overlap
        + 0.25 * ast_sim
        + 0.15 * fix_overlap
        + 0.15 * name_sim
    )


def find_duplicates(
    tests: list[TestMeta],
    cov_map: CoverageMap,
    fixture_index: FixtureIndex,
    min_score: float = 0.85,
) -> list[DuplicateFinding]:
    """Return pairs of tests that are likely duplicates."""
    findings: list[DuplicateFinding] = []
    seen: set[frozenset[str]] = set()

    for i, test_a in enumerate(tests):
        for test_b in tests[i + 1 :]:
            pair = frozenset({test_a.node_id, test_b.node_id})
            if pair in seen:
                continue
            seen.add(pair)

            cov_overlap = cov_map.overlap(test_a.node_id, test_b.node_id)
            fix_overlap = fixture_index.fixture_overlap(test_a.node_id, test_b.node_id)

            # Derive file and function name from node_id
            parts_a = test_a.node_id.split("::")
            parts_b = test_b.node_id.split("::")
            file_a = parts_a[0] if parts_a else test_a.file
            file_b = parts_b[0] if parts_b else test_b.file
            name_a = parts_a[-1] if parts_a else test_a.name
            name_b = parts_b[-1] if parts_b else test_b.name

            ast_sim = _ast_similarity(file_a, name_a, file_b, name_b)
            name_sim = _name_similarity(name_a, name_b)

            score = _duplicate_score(cov_overlap, ast_sim, fix_overlap, name_sim)
            if score >= min_score:
                findings.append(
                    DuplicateFinding(
                        test_a=test_a.node_id,
                        test_b=test_b.node_id,
                        score=round(score, 3),
                        coverage_overlap=round(cov_overlap, 3),
                        ast_similarity=round(ast_sim, 3),
                        fixture_overlap=round(fix_overlap, 3),
                        name_similarity=round(name_sim, 3),
                    )
                )

    return sorted(findings, key=lambda f: f.score, reverse=True)
