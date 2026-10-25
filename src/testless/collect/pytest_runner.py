"""Run pytest and collect test metadata via subprocess."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from testless.models.findings import TestMeta

# Loaded from this invocation's private scratch directory, independently of the
# target's pytest plugins. Passing pytest 9 subtests increment JUnit's suite
# counter without producing testcase elements. Record the actual reports and
# collected parent IDs; XML counters alone cannot prove that difference.
_ACCOUNTING_PLUGIN = '''import json
import os
from pathlib import Path

collected = []
finished = set()
passed_subtests = 0
identities = {}

def pytest_collection_finish(session):
    for item in session.items:
        # An external config such as -c /dev/null can omit the file prefix.
        # Retain the actual item's path and its collected parent/class suffix.
        suffix = item.nodeid.split("::", 1)[1]
        nodeid = Path(os.path.relpath(item.path, Path.cwd())).as_posix() + "::" + suffix
        identities[item.nodeid] = nodeid
        collected.append(nodeid)

def pytest_runtest_logreport(report):
    global passed_subtests
    if type(report).__module__ == "_pytest.subtests" and type(report).__name__ == "SubtestReport":
        if report.passed:
            passed_subtests += 1
    elif report.when == "call" or (report.when == "setup" and report.skipped):
        finished.add(identities.get(report.nodeid, report.nodeid))

def pytest_sessionfinish(session, exitstatus):
    Path(os.environ["TESTLESS_ACCOUNTING_PATH"]).write_text(json.dumps({
        "schema": "testless.pytest-accounting/v1",
        "run_id": os.environ["TESTLESS_ACCOUNTING_RUN_ID"],
        "collected": collected,
        "finished": sorted(finished),
        "passed_subtests": passed_subtests,
        "rootdir": str(session.config.rootpath),
        "cwd": str(Path.cwd()),
    }), encoding="utf-8")
'''


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
    The coverage JSON, with validated outcomes in the testless.scan/v1
    metadata, is atomically published to *coverage_dir*/coverage.json.
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
        accounting_path = run_dir / "accounting.json"
        run_id = uuid.uuid4().hex
        plugin = "_testless_accounting_" + run_id
        (run_dir / (plugin + ".py")).write_text(_ACCOUNTING_PLUGIN, encoding="utf-8")
        cmd = [python_bin, "-m", "pytest", "--tb=no", "-q"]
        cmd += extra_args or []
        cmd += [
            "-p", plugin,
            f"--cov={cov_source}", f"--cov-report=json:{json_path}",
            "--cov-context=test", f"--junitxml={report_path}", "-o", "junit_family=xunit1",
        ]
        cmd += test_dirs
        run_env = os.environ.copy()
        run_env["COVERAGE_FILE"] = str(cov_db)
        run_env["PYTHONPATH"] = str(run_dir) + os.pathsep + run_env.get("PYTHONPATH", "")
        run_env["TESTLESS_ACCOUNTING_PATH"] = str(accounting_path)
        run_env["TESTLESS_ACCOUNTING_RUN_ID"] = run_id
        try:
            child = subprocess.run(cmd, env=run_env, capture_output=False, text=True)  # noqa: S603
        except OSError as exc:
            raise PytestRunError(f"Cannot start pytest: {exc}") from exc
        if child.returncode != 0:
            raise PytestRunError(f"pytest exited with status {child.returncode}; scan is incomplete.", child.returncode)

        accounting = _load_accounting(accounting_path, run_id)
        tests = _parse_junit(report_path, accounting=accounting)
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

        # One public artifact binds validated outcomes to coverage. A single
        # atomic replacement commits the complete scan; publication failure
        # leaves the earlier complete artifact intact.
        destination = cov_dir / "coverage.json"
        try:
            coverage["testless"] = {
                "schema": "testless.scan/v1",
                "observation_id": uuid.uuid4().hex,
                "junit_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                "accounting_sha256": hashlib.sha256(accounting_path.read_bytes()).hexdigest(),
                "passed_subtests": accounting["passed_subtests"],
                "outcomes": [test.model_dump(mode="json") for test in tests],
            }
            json_path.write_text(json.dumps(coverage, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            os.replace(json_path, destination)
        except (OSError, ValueError, TypeError) as exc:
            raise PytestRunError(f"Cannot publish complete pytest scan: {exc}") from exc
        return tests, destination


class PytestRunError(RuntimeError):
    """The current child invocation cannot substantiate a complete scan."""

    def __init__(self, message: str, returncode: int = 1):
        super().__init__(message)
        self.returncode = returncode if returncode in (1, 2, 3, 4, 5) else 1


def _load_accounting(path: Path, run_id: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict)
                or set(data) != {"schema", "run_id", "collected", "finished", "passed_subtests", "rootdir", "cwd"}
                or data["schema"] != "testless.pytest-accounting/v1" or data["run_id"] != run_id
                or type(data["passed_subtests"]) is not int or data["passed_subtests"] < 0
                or data["cwd"] != str(Path.cwd()) or not isinstance(data["rootdir"], str)
                or not Path(data["rootdir"]).is_absolute()):
            raise ValueError("invalid accounting binding or counters")
        for key in ("collected", "finished"):
            ids = data[key]
            if (not isinstance(ids, list) or not ids or any(not isinstance(x, str) or "::" not in x for x in ids)
                    or len(set(ids)) != len(ids)):
                raise ValueError("missing or repeated parent identities")
        if set(data["collected"]) != set(data["finished"]):
            raise ValueError("collected parents did not finish")
        return data
    except (OSError, ValueError, TypeError) as exc:
        raise PytestRunError(f"Missing or invalid fresh pytest accounting: {exc}") from exc


def _parse_junit(path: Path, *, accounting: dict | None = None) -> list[TestMeta]:
    try:
        root = ET.parse(path).getroot()
        cases = list(root.iter("testcase"))
        if root.tag not in ("testsuites", "testsuite") or not cases:
            raise ValueError("no test outcomes")
        suites = [suite for suite in root.iter("testsuite") if suite.find("testsuite") is None]
        passed_subtests = accounting["passed_subtests"] if accounting is not None else 0
        if not suites or sum(int(suite.attrib["tests"]) for suite in suites) != len(cases) + passed_subtests:
            raise ValueError("incomplete test outcomes")
        if any(int(suite.get(key, "0")) != 0 for suite in suites for key in ("failures", "errors")):
            raise ValueError("failed suite outcome despite zero pytest exit")
        tests = []
        for case in cases:
            file_path = case.get("file", "")
            name = case.get("name", "")
            if not file_path or not name:
                raise ValueError("missing test identity")
            if accounting is not None:
                file_path = Path(os.path.relpath(
                    Path(accounting["rootdir"]) / file_path, accounting["cwd"])).as_posix()
            if case.find("failure") is not None or case.find("error") is not None:
                raise ValueError("failed test outcome despite zero pytest exit")
            module = str(Path(file_path).with_suffix("")).replace("/", ".").replace("\\", ".")
            classname = case.get("classname", "").removeprefix(".")
            # Pytest may import a non-package test directory by module basename.
            candidates = (module, module.rsplit(".", 1)[-1])
            prefix = next((m for m in candidates if classname == m or classname.startswith(m + ".")), None)
            class_path = (classname[len(prefix) + 1:] if classname != prefix else "") if prefix is not None else classname
            parts = [file_path] + (class_path.split(".") if class_path else []) + [name]
            tests.append(TestMeta(
                node_id="::".join(parts), file=file_path, name="::".join(parts[1:]),
                duration=float(case.get("time", "0")),
                status="skipped" if case.find("skipped") is not None else "passed",
            ))
        if accounting is not None:
            ids = [test.node_id for test in tests]
            if len(ids) != len(set(ids)) or set(ids) != set(accounting["collected"]):
                raise ValueError("JUnit parents differ from collected and completed tests")
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
