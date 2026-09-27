"""Tests for the tickets builder and serializer."""

from __future__ import annotations

from pathlib import Path

from testless.models.findings import (
    AnalysisReport,
    DeadTestFinding,
    DuplicateFinding,
    MissingTestFinding,
    RefactorFinding,
)
from testless.models.planfile import PlanfileKind
from testless.tickets.builder import build_duplicate_ticket, build_planfiles
from testless.tickets.prompts import attach_prompt
from testless.tickets.serializer import write_planfiles, write_summary_json


def test_build_duplicate_ticket():
    finding = DuplicateFinding(
        test_a="tests/test_a.py::test_foo",
        test_b="tests/test_b.py::test_foo_copy",
        score=0.92,
    )
    ticket = build_duplicate_ticket(finding)
    assert ticket.kind == PlanfileKind.duplicate
    assert "test_foo" in ticket.title
    assert ticket.impact.risk.value == "low"
    assert len(ticket.tasks) > 0
    assert len(ticket.acceptance_criteria) > 0


def test_build_planfiles_from_report():
    report = AnalysisReport(
        duplicates=[DuplicateFinding(test_a="a::t1", test_b="b::t2", score=0.9)],
        dead_tests=[DeadTestFinding(node_id="c::t3", file="c.py")],
        missing_tests=[MissingTestFinding(target="/health", test_type="smoke", description="add smoke")],
        refactor_candidates=[RefactorFinding(node_id="d::t4", file="d.py", reason="too slow")],
    )
    tickets = build_planfiles(report)
    assert len(tickets) == 4
    kinds = {t.kind for t in tickets}
    assert PlanfileKind.duplicate in kinds
    assert PlanfileKind.dead in kinds
    assert PlanfileKind.missing in kinds
    assert PlanfileKind.refactor in kinds


def test_write_planfiles(tmp_path: Path):
    report = AnalysisReport(
        duplicates=[DuplicateFinding(test_a="a::t1", test_b="b::t2", score=0.9)],
    )
    tickets = build_planfiles(report)
    written = write_planfiles(tickets, tmp_path / "planfiles")
    assert len(written) == 1
    assert written[0].suffix == ".yml"
    assert written[0].exists()


def test_write_summary_json(tmp_path: Path):
    report = AnalysisReport(
        dead_tests=[DeadTestFinding(node_id="x::test_dead", file="x.py")],
    )
    tickets = build_planfiles(report)
    summary = write_summary_json(tickets, tmp_path / "planfiles")
    assert summary.exists()
    import json
    data = json.loads(summary.read_text())
    assert isinstance(data, list)
    assert len(data) == 1


def test_attach_prompt():
    report = AnalysisReport(
        duplicates=[DuplicateFinding(test_a="a::t1", test_b="b::t2", score=0.9)],
    )
    tickets = build_planfiles(report)
    with_prompts = [attach_prompt(t) for t in tickets]
    assert "system_prompt" in with_prompts[0].llm_hints
    assert len(with_prompts[0].llm_hints["system_prompt"]) > 0
