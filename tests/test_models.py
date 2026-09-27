"""Tests for testless models."""

from __future__ import annotations

from testless.models.coverage_map import CoverageMap, FileCoverage
from testless.models.findings import (
    AnalysisReport,
    DeadTestFinding,
    DuplicateFinding,
    MissingTestFinding,
)
from testless.models.planfile import Planfile, PlanfileKind, RiskLevel

# ---------------------------------------------------------------------------
# Planfile
# ---------------------------------------------------------------------------

def test_planfile_roundtrip_yaml():
    pf = Planfile(
        kind=PlanfileKind.duplicate,
        id="DUP-001",
        title="Remove duplicate test",
        goal="Reduce redundancy",
    )
    yaml_text = pf.to_yaml()
    loaded = Planfile.from_yaml(yaml_text)
    assert loaded.id == "DUP-001"
    assert loaded.kind == PlanfileKind.duplicate
    assert loaded.title == "Remove duplicate test"


def test_planfile_default_llm_hints():
    pf = Planfile(
        kind=PlanfileKind.missing,
        id="MISS-001",
        title="Add smoke test",
        goal="Improve coverage",
    )
    assert pf.llm_hints["safe_refactor"] is True
    assert pf.llm_hints["style"] == "minimal change"


def test_planfile_impact_default():
    pf = Planfile(
        kind=PlanfileKind.dead,
        id="DEAD-001",
        title="Remove dead test",
        goal="Clean up",
    )
    assert pf.impact.risk == RiskLevel.low


# ---------------------------------------------------------------------------
# CoverageMap
# ---------------------------------------------------------------------------

def test_coverage_map_overlap_identical():
    fc = FileCoverage(path="src/app.py", line_to_tests={1: ["a", "b"], 2: ["a", "b"]})
    cmap = CoverageMap(files={"src/app.py": fc})
    assert cmap.overlap("a", "b") == 1.0


def test_coverage_map_overlap_disjoint():
    fc = FileCoverage(path="src/app.py", line_to_tests={1: ["a"], 2: ["b"]})
    cmap = CoverageMap(files={"src/app.py": fc})
    assert cmap.overlap("a", "b") == 0.0


def test_coverage_map_overlap_partial():
    fc = FileCoverage(
        path="src/app.py",
        line_to_tests={1: ["a", "b"], 2: ["a"], 3: ["b"]},
    )
    cmap = CoverageMap(files={"src/app.py": fc})
    # intersection = {line 1}, union = {1, 2, 3}
    assert abs(cmap.overlap("a", "b") - 1 / 3) < 1e-9


def test_coverage_map_unique_lines():
    fc = FileCoverage(
        path="src/app.py",
        line_to_tests={1: ["a", "b"], 2: ["a"], 3: ["b"]},
    )
    unique_a = fc.unique_lines_for("a", ["a", "b"])
    unique_b = fc.unique_lines_for("b", ["a", "b"])
    assert unique_a == {2}
    assert unique_b == {3}


# ---------------------------------------------------------------------------
# AnalysisReport
# ---------------------------------------------------------------------------

def test_analysis_report_empty():
    report = AnalysisReport()
    assert report.duplicates == []
    assert report.dead_tests == []
    assert report.missing_tests == []
    assert report.refactor_candidates == []


def test_analysis_report_with_findings():
    report = AnalysisReport(
        duplicates=[DuplicateFinding(test_a="tests/a.py::test_x", test_b="tests/b.py::test_y", score=0.9)],
        dead_tests=[DeadTestFinding(node_id="tests/c.py::test_z", file="tests/c.py")],
        missing_tests=[MissingTestFinding(target="/health", test_type="smoke", description="add smoke test")],
    )
    assert len(report.duplicates) == 1
    assert len(report.dead_tests) == 1
    assert len(report.missing_tests) == 1
