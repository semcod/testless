"""Identify tests that are good candidates for refactoring."""

from __future__ import annotations

import ast
from pathlib import Path

from testless.models.findings import RefactorFinding, TestMeta

_MAX_ASSERTIONS = 10
_MAX_DURATION_S = 5.0
_MAX_LINES = 80


def _count_assertions(file: str, func_name: str) -> int:
    path = Path(file)
    if not path.exists():
        return 0
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == func_name:
            return sum(
                1
                for child in ast.walk(node)
                if isinstance(child, ast.Assert)
                or (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr.startswith("assert")
                )
            )
    return 0


def _count_lines(file: str, func_name: str) -> int:
    path = Path(file)
    if not path.exists():
        return 0
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == func_name:
            end = getattr(node, "end_lineno", node.lineno)
            return end - node.lineno + 1
    return 0


def find_refactor_candidates(tests: list[TestMeta]) -> list[RefactorFinding]:
    """Return tests that warrant refactoring."""
    findings: list[RefactorFinding] = []

    for test in tests:
        parts = test.node_id.split("::")
        file = parts[0] if parts else test.file
        func_name = parts[-1] if len(parts) > 1 else test.name

        reasons: list[str] = []

        if test.duration > _MAX_DURATION_S:
            reasons.append(f"slow test ({test.duration:.1f}s > {_MAX_DURATION_S}s threshold)")

        assertions = _count_assertions(file, func_name)
        if assertions > _MAX_ASSERTIONS:
            reasons.append(f"too many assertions ({assertions} > {_MAX_ASSERTIONS})")

        lines = _count_lines(file, func_name)
        if lines > _MAX_LINES:
            reasons.append(f"test function too long ({lines} lines > {_MAX_LINES})")

        if reasons:
            findings.append(
                RefactorFinding(
                    node_id=test.node_id,
                    file=file,
                    reason="; ".join(reasons),
                )
            )

    return findings
