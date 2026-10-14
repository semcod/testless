"""Detect duplicate tests using coverage overlap, AST similarity, fixtures and names."""

from __future__ import annotations

import ast
import difflib
from pathlib import Path

from testless.collect.fixture_index import FixtureIndex
from testless.models.coverage_map import CoverageMap
from testless.models.findings import DuplicateFinding, TestMeta


def _ast_similarity(
    file_a: str, name_a: str, file_b: str, name_b: str,
    *, source_cache: dict[str, dict[str, str]] | None = None,
) -> float:
    """Compute normalized edit-distance similarity between two test function bodies."""

    sources = {} if source_cache is None else source_cache

    def _get_source(file: str, name: str) -> str:
        if file in sources:
            return sources[file].get(name, "")
        sources[file] = {}
        path = Path(file)
        if not path.exists():
            return ""
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name not in sources[file]:
                sources[file][node.name] = ast.unparse(node)
        return sources[file].get(name, "")

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
    # Snapshot data once per analysis, never across invocations. Parsing and
    # coverage lookup previously repeated for every pair (quadratic file I/O).
    sources: dict[str, dict[str, str]] = {}
    coverage: dict[str, set[tuple[str, int]]] = {test.node_id: set() for test in tests}
    fixtures = {test.node_id: set(fixture_index.fixtures_for(test.node_id)) for test in tests}
    for path, file_coverage in cov_map.files.items():
        for line, node_ids in file_coverage.line_to_tests.items():
            for node_id in node_ids:
                if node_id in coverage:
                    coverage[node_id].add((path, line))

    for i, test_a in enumerate(tests):
        for test_b in tests[i + 1 :]:
            pair = frozenset({test_a.node_id, test_b.node_id})
            if pair in seen:
                continue
            seen.add(pair)

            lines_a, lines_b = coverage[test_a.node_id], coverage[test_b.node_id]
            union = lines_a | lines_b
            cov_overlap = len(lines_a & lines_b) / len(union) if union else 0.0
            fa, fb = fixtures[test_a.node_id], fixtures[test_b.node_id]
            fixture_union = fa | fb
            fix_overlap = len(fa & fb) / len(fixture_union) if fixture_union else 0.0
            # The same arithmetic order gives an upper bound on the score.
            # Equality must still be analyzed because the threshold is inclusive.
            if _duplicate_score(cov_overlap, 1.0, fix_overlap, 1.0) < min_score:
                continue

            # Derive file and function name from node_id
            parts_a = test_a.node_id.split("::")
            parts_b = test_b.node_id.split("::")
            file_a = parts_a[0] if parts_a else test_a.file
            file_b = parts_b[0] if parts_b else test_b.file
            name_a = parts_a[-1] if parts_a else test_a.name
            name_b = parts_b[-1] if parts_b else test_b.name

            ast_sim = _ast_similarity(file_a, name_a, file_b, name_b, source_cache=sources)
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
