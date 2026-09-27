"""Run pytest and collect test metadata via subprocess."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from testless.models.findings import TestMeta


def resolve_python_executable(custom_python: str | None = None) -> str:
    """Resolve the appropriate Python executable (custom, venv, or current)."""
    if custom_python and Path(custom_python).is_file():
        return str(Path(custom_python).absolute())
    import os
    if "VIRTUAL_ENV" in os.environ:
        venv_root = Path(os.environ["VIRTUAL_ENV"])
        for candidate in (
            venv_root / "bin" / "python",
            venv_root / "bin" / "python3",
            venv_root / "Scripts" / "python.exe",
        ):
            if candidate.is_file():
                return str(candidate.absolute())
    for rel in (
        ".venv/bin/python",
        ".venv/bin/python3",
        "venv/bin/python",
        "venv/bin/python3",
        ".venv/Scripts/python.exe",
        "venv/Scripts/python.exe",
    ):
        candidate = Path(rel)
        if candidate.is_file():
            return str(candidate.absolute())
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        prefix_root = Path(sys.prefix)
        for candidate in (
            prefix_root / "bin" / "python",
            prefix_root / "bin" / "python3",
            prefix_root / "Scripts" / "python.exe",
        ):
            if candidate.is_file():
                return str(candidate.absolute())
    return sys.executable


def run_pytest(
    packages: list[str],
    test_dirs: list[str],
    coverage_dir: str = ".coverage_data",
    extra_args: list[str] | None = None,
    python_executable: str | None = None,
) -> tuple[list[TestMeta], Path]:
    """
    Run pytest with coverage contexts enabled and collect test metadata.

    Returns a tuple of (list[TestMeta], coverage_json_path).
    The coverage JSON is written to *coverage_dir*/coverage.json.
    """
    cov_dir = Path(coverage_dir)
    cov_dir.mkdir(parents=True, exist_ok=True)
    json_path = cov_dir / "coverage.json"

    # Auto-detect source package or directory if not explicitly provided
    if packages:
        cov_source = ",".join(packages)
    elif Path("src").is_dir():
        cov_source = "src"
    else:
        cov_source = "."

    python_bin = resolve_python_executable(python_executable)

    cmd = [
        python_bin,
        "-m",
        "pytest",
        "--tb=no",
        "-q",
        f"--cov={cov_source}",
        f"--cov-report=json:{json_path}",
        "--cov-context=test",
    ]

    import importlib.util

    if importlib.util.find_spec("pytest_jsonreport") is not None:
        cmd.extend([
            "--json-report",
            f"--json-report-file={cov_dir / 'report.json'}",
        ])

    cmd += extra_args or []
    cmd += test_dirs

    import os

    cov_db = cov_dir / ".coverage"
    run_env = os.environ.copy()
    run_env["COVERAGE_FILE"] = str(cov_db)

    subprocess.run(cmd, env=run_env, capture_output=False, text=True)  # noqa: S603

    # Ensure coverage.json is generated with line contexts via coverage CLI
    try:
        subprocess.run(
            [
                python_bin,
                "-m",
                "coverage",
                "json",
                f"--data-file={cov_db}",
                "--show-contexts",
                "-o",
                str(json_path),
            ],
            env=run_env,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        pass

    # Parse the pytest JSON report if available
    report_path = cov_dir / "report.json"
    tests: list[TestMeta] = []
    if report_path.exists():
        tests = _parse_report(report_path)

    # Fallback: extract tests from coverage map contexts if report.json is absent
    if not tests and json_path.exists():
        from testless.collect.coverage_loader import load_coverage_json

        cov_map = load_coverage_json(json_path)
        all_node_ids: set[str] = set()
        for fc in cov_map.files.values():
            for tests_list in fc.line_to_tests.values():
                all_node_ids.update(tests_list)
        tests = [
            TestMeta(
                node_id=nid,
                file=nid.split("::")[0],
                name=nid.split("::")[-1],
                status="passed",
            )
            for nid in sorted(all_node_ids)
        ]

    return tests, json_path


def _parse_report(report_path: Path) -> list[TestMeta]:
    """Parse pytest-json-report output into TestMeta objects."""
    with report_path.open() as fh:
        data = json.load(fh)

    tests: list[TestMeta] = []
    for test in data.get("tests", []):
        node_id = test.get("nodeid", "")
        parts = node_id.split("::")
        file_path = parts[0] if parts else ""
        name = "::".join(parts[1:]) if len(parts) > 1 else node_id
        tests.append(
            TestMeta(
                node_id=node_id,
                file=file_path,
                name=name,
                duration=test.get("call", {}).get("duration", 0.0),
                status=test.get("outcome", "unknown"),
            )
        )
    return tests
