"""Load coverage.py JSON output (with --cov-context=test) into a CoverageMap."""

from __future__ import annotations

import json
from pathlib import Path

from testless.models.coverage_map import CoverageMap, FileCoverage


def _clean_node_id(raw_context: str) -> str:
    ctx = raw_context.strip()
    if "|" in ctx:
        parts = ctx.split("|")
        for p in parts:
            if "::" in p:
                return p
        return parts[0]
    return ctx


def load_coverage_json(json_path: str | Path) -> CoverageMap:
    """
    Parse a coverage.json file produced by::

        pytest --cov=<pkg> --cov-report=json --cov-context=test
        or coverage json --show-contexts

    Returns a :class:`CoverageMap` with per-line, per-test context data.
    """
    path = Path(json_path)
    if not path.exists():
        return CoverageMap()

    with path.open() as fh:
        data = json.load(fh)

    cmap = CoverageMap()
    for file_path, file_data in data.get("files", {}).items():
        fc = FileCoverage(path=file_path)

        contexts: dict = file_data.get("contexts", {})
        if not contexts:
            continue

        for k, v in contexts.items():
            # Check if key is a line number (standard coverage.py 7.x schema: {str(line): [context_names]})
            is_line_key = False
            try:
                line_num = int(k)
                is_line_key = True
            except ValueError:
                is_line_key = False

            if is_line_key and isinstance(v, list):
                tests_for_line: list[str] = []
                for raw_ctx in v:
                    if not raw_ctx or raw_ctx == "test":
                        continue
                    node_id = _clean_node_id(raw_ctx)
                    if node_id and node_id not in tests_for_line:
                        tests_for_line.append(node_id)
                if tests_for_line:
                    fc.line_to_tests.setdefault(line_num, [])
                    for node_id in tests_for_line:
                        if node_id not in fc.line_to_tests[line_num]:
                            fc.line_to_tests[line_num].append(node_id)
            else:
                # Legacy / mock schema: {context_name: [line_numbers]}
                node_id = _clean_node_id(str(k))
                if isinstance(v, list):
                    for ln in v:
                        if isinstance(ln, int):
                            fc.line_to_tests.setdefault(ln, [])
                            if node_id not in fc.line_to_tests[ln]:
                                fc.line_to_tests[ln].append(node_id)

        if fc.line_to_tests:
            cmap.files[file_path] = fc

    return cmap

