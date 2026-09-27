"""Index fixtures used by each test via AST analysis."""

from __future__ import annotations

import ast
from pathlib import Path


class FixtureIndex:
    """Map test node IDs to their declared fixture parameters."""

    _IGNORED_PARTS = {
        ".venv", "venv", ".git", ".worktrees", "node_modules",
        "build", "dist", ".tox", "__pycache__", ".subactor", ".planfile"
    }

    def __init__(self) -> None:
        self._test_fixtures: dict[str, list[str]] = {}
        self._fixture_defs: dict[str, str] = {}  # fixture name -> file

    def scan_directory(self, directory: str | Path) -> None:
        """Recursively scan a directory for test files and conftest.py."""
        root = Path(directory)
        for py_file in root.rglob("*.py"):
            if any(
                part in self._IGNORED_PARTS or (part.startswith(".") and part not in (".", ".."))
                for part in py_file.parts[:-1]
            ):
                continue
            self._scan_file(py_file)

    def _scan_file(self, path: Path) -> None:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self._process_function(node, path)

    def _process_function(self, node: ast.FunctionDef, path: Path) -> None:
        # Record fixture definitions
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Attribute)
                and decorator.attr == "fixture"
            ) or (isinstance(decorator, ast.Name) and decorator.id == "fixture"):
                self._fixture_defs[node.name] = str(path)

        # Record test fixture usage (parameters = fixtures)
        if node.name.startswith("test_") or node.name.startswith("Test"):
            args = [arg.arg for arg in node.args.args if arg.arg != "self"]
            if args:
                rel_path = str(path)
                node_id = f"{rel_path}::{node.name}"
                self._test_fixtures[node_id] = args

    def fixtures_for(self, node_id: str) -> list[str]:
        """Return fixture list for a test, matching by suffix if needed."""
        if node_id in self._test_fixtures:
            return self._test_fixtures[node_id]
        # Try matching by the function name part only
        func_name = node_id.split("::")[-1]
        for key, val in self._test_fixtures.items():
            if key.endswith(f"::{func_name}"):
                return val
        return []

    def all_defined_fixtures(self) -> set[str]:
        return set(self._fixture_defs.keys())

    def fixture_overlap(self, node_a: str, node_b: str) -> float:
        """Jaccard overlap of fixtures between two tests (0–1)."""
        fa = set(self.fixtures_for(node_a))
        fb = set(self.fixtures_for(node_b))
        if not fa and not fb:
            return 0.0
        union = fa | fb
        intersection = fa & fb
        return len(intersection) / len(union)
