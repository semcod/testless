"""Outcome evidence must come from this pytest invocation, never coverage contexts."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from testless.cli import main
from testless.collect import pytest_runner as collector


@pytest.fixture
def target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('NO_AUTOUPDATE', '1')
    monkeypatch.setenv('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    monkeypatch.setenv('PYTHONPATH', str(tmp_path))
    monkeypatch.setattr(collector, 'resolve_python_executable', lambda _: sys.executable)
    (tmp_path / 'subject.py').write_text('def answer():\n    return 42\n')
    (tmp_path / '.coveragerc').write_text('[run]\n')
    return tmp_path


def scan(target, text, extra=None):
    (target / 'test_subject.py').write_text(text)
    return collector.run_pytest(['subject'], ['test_subject.py'], str(target / 'cov'),
        extra_args=['-p', 'pytest_cov', '-c', '/dev/null'] + (extra or []))


@pytest.mark.parametrize('text', [
    'from subject import answer\ndef test_fail():\n    assert answer() == 0\n',
    'import deliberately_missing_testless_dependency\n',
    '# no tests\n',
])
def test_child_failure_never_returns_success(target, text):
    with pytest.raises(RuntimeError, match='pytest'):
        scan(target, text)


def test_real_pass_has_observed_outcome(target):
    tests, path = scan(target, 'from subject import answer\ndef test_pass():\n    assert answer() == 42\n')
    assert {t.name: t.status for t in tests} == {'test_pass': 'passed'}
    assert path.is_file()


def test_skipped_outcome_is_preserved_from_fresh_junit(target, monkeypatch):
    junit = JUNIT.replace('/>', '><skipped message="fixture outcome"/></testcase>')
    fake_run(monkeypatch, junit=junit, coverage=COVERAGE)
    tests, path = scan(target, '# controlled child report')
    assert {t.name: t.status for t in tests} == {'test_pass': 'skipped'}
    assert path.is_file()


def test_cli_propagates_child_failure_without_collected_success(target, monkeypatch):
    (target / 'test_subject.py').write_text('import deliberately_missing_testless_dependency\n')
    # Plugin auto-loading is explicitly disabled in this isolated child fixture.
    from testless.config import TestlessConfig
    monkeypatch.setattr('testless.cli.load_config', lambda _: TestlessConfig(
        packages=['subject'], test_dirs=['test_subject.py'],
        pytest_args=['-p', 'pytest_cov', '-c', '/dev/null']))
    result = CliRunner().invoke(main, ['scan', '--out', str(target / 'cov')])
    assert result.exit_code != 0
    assert 'Collected ' not in result.output
    assert 'pytest' in result.output.lower()


def fake_run(monkeypatch, *, code=0, junit=None, coverage=None, coverage_code=0):
    def run(cmd, **kwargs):
        if cmd[2] == 'pytest':
            for arg in cmd:
                if arg.startswith('--junitxml=') and junit is not None:
                    Path(arg.split('=', 1)[1]).write_text(junit)
                if arg.startswith('--cov-report=json:') and coverage is not None:
                    Path(arg.split(':', 1)[1]).write_text(coverage)
            return subprocess.CompletedProcess(cmd, code)
        return subprocess.CompletedProcess(cmd, coverage_code)
    monkeypatch.setattr(collector.subprocess, 'run', run)


JUNIT = '<testsuites><testsuite tests="1"><testcase file="test_subject.py" classname="test_subject" name="test_pass" time="0.1"/></testsuite></testsuites>'
COVERAGE = json.dumps({'files': {'subject.py': {'contexts': {'1': ['test_subject.py::test_pass|run']}}}})


@pytest.mark.parametrize('code', [1, 2, 3, 4, 5])
def test_stale_reports_cannot_mask_nonzero_child(target, monkeypatch, code):
    cov = target / 'cov'
    cov.mkdir()
    (cov / 'report.json').write_text('{"tests":[{"nodeid":"stale.py::test_old","outcome":"passed"}]}')
    (cov / 'coverage.json').write_text(COVERAGE)
    fake_run(monkeypatch, code=code)
    with pytest.raises(RuntimeError, match='pytest'):
        scan(target, '# mock child')


@pytest.mark.parametrize('junit', [None, '<broken', '<testsuites/>'])
def test_missing_malformed_or_empty_outcomes_fail_closed(target, monkeypatch, junit):
    fake_run(monkeypatch, junit=junit, coverage=COVERAGE)
    with pytest.raises(RuntimeError):
        scan(target, '# mock child')


def test_zero_exit_conflicting_failed_outcome_rejected(target, monkeypatch):
    fake_run(monkeypatch, junit=JUNIT.replace('/>', '><failure>bad</failure></testcase>'), coverage=COVERAGE)
    with pytest.raises(RuntimeError):
        scan(target, '# mock child')


@pytest.mark.parametrize('coverage', [None, '{broken', '{}'])
def test_missing_or_invalid_fresh_coverage_rejected(target, monkeypatch, coverage):
    fake_run(monkeypatch, junit=JUNIT, coverage=coverage)
    with pytest.raises(RuntimeError):
        scan(target, '# mock child')


def test_coverage_export_failure_rejected(target, monkeypatch):
    fake_run(monkeypatch, junit=JUNIT, coverage=COVERAGE, coverage_code=1)
    with pytest.raises(RuntimeError):
        scan(target, '# mock child')


@pytest.mark.parametrize('junit', [
    JUNIT.replace('tests="1"', 'tests="2"'),
    JUNIT.replace('tests="1"', 'tests="1" errors="1"'),
    JUNIT.replace('tests="1"', ''),
    JUNIT.replace('file="test_subject.py"', ''),
])
def test_partial_or_unidentified_outcomes_rejected(target, monkeypatch, junit):
    fake_run(monkeypatch, junit=junit, coverage=COVERAGE)
    with pytest.raises(RuntimeError):
        scan(target, '# mock child')


def test_failed_invocation_preserves_previous_snapshot(target, monkeypatch):
    cov = target / 'cov'
    cov.mkdir()
    previous = {'coverage.json': COVERAGE, 'report.xml': JUNIT}
    for name, data in previous.items():
        (cov / name).write_text(data)
    fake_run(monkeypatch, code=2, junit=JUNIT, coverage=COVERAGE)
    with pytest.raises(RuntimeError):
        scan(target, '# mock child')
    assert {name: (cov / name).read_text() for name in previous} == previous
    assert not list(cov.glob('.pytest-run-*'))
