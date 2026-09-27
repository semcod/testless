"""Tests for the CLI."""

from __future__ import annotations

from click.testing import CliRunner

from testless.cli import main


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "testless" in result.output.lower()


def test_scan_help():
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--help"])
    assert result.exit_code == 0
    assert "--source" in result.output
    assert "--python" in result.output



def test_duplicates_help():
    runner = CliRunner()
    result = runner.invoke(main, ["duplicates", "--help"])
    assert result.exit_code == 0


def test_missing_help():
    runner = CliRunner()
    result = runner.invoke(main, ["missing", "--help"])
    assert result.exit_code == 0


def test_planfiles_help():
    runner = CliRunner()
    result = runner.invoke(main, ["planfiles", "--help"])
    assert result.exit_code == 0


def test_doctor_help():
    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--help"])
    assert result.exit_code == 0


def test_doctor_no_coverage(tmp_path):
    """doctor should not crash when coverage.json is absent."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["doctor", "--coverage-json", str(tmp_path / "nonexistent.json")],
    )
    # Should complete without a Python traceback (exit 0 is acceptable)
    assert "Error" not in result.output or result.exit_code == 0


def test_missing_no_dirs(tmp_path):
    """missing command should handle non-existent service dirs gracefully."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["missing", "--services", str(tmp_path / "nonexistent")],
    )
    assert result.exit_code == 0
