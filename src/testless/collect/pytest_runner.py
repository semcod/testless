"""Run pytest and collect test metadata via subprocess."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
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
    cov_dir = Path(coverage_dir).resolve()
    cov_dir.mkdir(parents=True, exist_ok=True)
    python_bin = resolve_python_executable(python_executable)
    cov_source = ",".join(packages) if packages else ("src" if Path("src").is_dir() else ".")

    # A child must not see outputs or a coverage database from an earlier scan.
    with tempfile.TemporaryDirectory(prefix=".pytest-run-", dir=cov_dir) as scratch:
        run_dir = Path(scratch)
        json_path = run_dir / "coverage.json"
        report_path = run_dir / "report.xml"
        cov_db = run_dir / ".coverage"
        cmd = [python_bin, "-m", "pytest", "--tb=no", "-q"]
        cmd += extra_args or []
        cmd += [
            f"--cov={cov_source}", f"--cov-report=json:{json_path}",
            "--cov-context=test", f"--junitxml={report_path}", "-o", "junit_family=xunit1",
        ]
        cmd += test_dirs
        run_env = os.environ.copy()
        run_env["COVERAGE_FILE"] = str(cov_db)
        try:
            child = subprocess.run(cmd, env=run_env, capture_output=False, text=True)  # noqa: S603
        except OSError as exc:
            raise PytestRunError(f"Cannot start pytest: {exc}") from exc
        if child.returncode != 0:
            raise PytestRunError(f"pytest exited with status {child.returncode}; scan is incomplete.", child.returncode)

        tests = _parse_junit(report_path)
        # Coverage contexts prove execution, never an outcome. Require the fresh
        # built-in pytest outcome report even when pytest-json-report is absent.
        try:
            exported = subprocess.run(
                [python_bin, "-m", "coverage", "json", f"--data-file={cov_db}",
                 "--show-contexts", "-o", str(json_path)],
                env=run_env, capture_output=True, text=True,
            )
            if exported.returncode != 0:
                raise PytestRunError("pytest coverage export failed; scan is incomplete.")
            coverage = json.loads(json_path.read_text())
            if not isinstance(coverage, dict) or not isinstance(coverage.get("files"), dict):
                raise ValueError("missing files object")
        except (OSError, ValueError) as exc:
            raise PytestRunError(f"Missing or invalid fresh pytest coverage report: {exc}") from exc

        # Retain the public coverage.json location only after both fresh reports
        # validate. A failed invocation preserves the previous successful scan.
        destination = cov_dir / "coverage.json"
        os.replace(json_path, destination)
        os.replace(report_path, cov_dir / "report.xml")
        return tests, destination


class PytestRunError(RuntimeError):
    """The current child invocation cannot substantiate a complete scan."""

    def __init__(self, message: str, returncode: int = 1):
        super().__init__(message)
        self.returncode = returncode if returncode in (1, 2, 3, 4, 5) else 1


def _parse_junit(path: Path) -> list[TestMeta]:
    try:
        root = ET.parse(path).getroot()
        cases = list(root.iter("testcase"))
        if root.tag not in ("testsuites", "testsuite") or not cases:
            raise ValueError("no test outcomes")
        suites = [suite for suite in root.iter("testsuite") if suite.find("testsuite") is None]
        if not suites or sum(int(suite.attrib["tests"]) for suite in suites) != len(cases):
            raise ValueError("incomplete test outcomes")
        if any(int(suite.get(key, "0")) != 0 for suite in suites for key in ("failures", "errors")):
            raise ValueError("failed suite outcome despite zero pytest exit")
        tests = []
        for case in cases:
            file_path = case.get("file", "")
            name = case.get("name", "")
            if not file_path or not name:
                raise ValueError("missing test identity")
            if case.find("failure") is not None or case.find("error") is not None:
                raise ValueError("failed test outcome despite zero pytest exit")
            module = str(Path(file_path).with_suffix("")).replace("/", ".").replace("\\", ".")
            classname = case.get("classname", "")
            class_path = classname[len(module) + 1:] if classname.startswith(module + ".") else ""
            parts = [file_path] + (class_path.split(".") if class_path else []) + [name]
            tests.append(TestMeta(
                node_id="::".join(parts), file=file_path, name="::".join(parts[1:]),
                duration=float(case.get("time", "0")),
                status="skipped" if case.find("skipped") is not None else "passed",
            ))
        return tests
    except (OSError, ET.ParseError, ValueError, KeyError) as exc:
        raise PytestRunError(f"Missing or invalid fresh pytest outcome report: {exc}") from exc


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
