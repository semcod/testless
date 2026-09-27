"""Tests for fixture_index and endpoint_inventory collectors."""

from __future__ import annotations

import textwrap
from pathlib import Path

from testless.collect.endpoint_inventory import EndpointInventory
from testless.collect.fixture_index import FixtureIndex

# ---------------------------------------------------------------------------
# FixtureIndex
# ---------------------------------------------------------------------------

def test_fixture_index_detects_fixtures(tmp_path: Path):
    test_file = tmp_path / "test_example.py"
    test_file.write_text(
        textwrap.dedent("""\
            import pytest

            @pytest.fixture
            def my_db():
                return {}

            def test_something(my_db, client):
                assert my_db == {}
        """)
    )
    index = FixtureIndex()
    index.scan_directory(tmp_path)

    assert "my_db" in index.all_defined_fixtures()
    fixtures = index.fixtures_for(f"{test_file}::test_something")
    assert "my_db" in fixtures
    assert "client" in fixtures


def test_fixture_overlap_same_fixtures(tmp_path: Path):
    test_file = tmp_path / "test_dup.py"
    test_file.write_text(
        textwrap.dedent("""\
            def test_a(client, db):
                pass

            def test_b(client, db):
                pass
        """)
    )
    index = FixtureIndex()
    index.scan_directory(tmp_path)

    overlap = index.fixture_overlap(f"{test_file}::test_a", f"{test_file}::test_b")
    assert overlap == 1.0


def test_fixture_overlap_no_fixtures(tmp_path: Path):
    index = FixtureIndex()
    assert index.fixture_overlap("tests/a.py::test_x", "tests/b.py::test_y") == 0.0


# ---------------------------------------------------------------------------
# EndpointInventory
# ---------------------------------------------------------------------------

def test_endpoint_inventory_flask_style(tmp_path: Path):
    app_file = tmp_path / "views.py"
    app_file.write_text(
        textwrap.dedent("""\
            from flask import Flask
            app = Flask(__name__)

            @app.route('/health', methods=['GET'])
            def health_check():
                return 'ok'

            @app.route('/users', methods=['POST'])
            def create_user():
                return 'created'
        """)
    )
    inv = EndpointInventory()
    inv.scan_directory(tmp_path)

    paths = {e.path for e in inv.endpoints}
    assert "/health" in paths
    assert "/users" in paths


def test_endpoint_inventory_skips_test_files(tmp_path: Path):
    test_file = tmp_path / "test_views.py"
    test_file.write_text(
        textwrap.dedent("""\
            @app.route('/should_not_appear')
            def test_something():
                pass
        """)
    )
    inv = EndpointInventory()
    inv.scan_directory(tmp_path)
    paths = {e.path for e in inv.endpoints}
    assert "/should_not_appear" not in paths


def test_endpoint_inventory_detects_sql_service(tmp_path: Path):
    svc_file = tmp_path / "user_service.py"
    svc_file.write_text(
        textwrap.dedent("""\
            import sqlite3

            def get_users(conn):
                return conn.execute('SELECT * FROM users').fetchall()
        """)
    )
    inv = EndpointInventory()
    inv.scan_directory(tmp_path)
    sql_services = [s for s in inv.services if s.has_sql]
    assert len(sql_services) >= 1


def test_run_pytest_resilient(tmp_path: Path):
    from testless.collect.pytest_runner import run_pytest

    cov_dir = tmp_path / "cov"
    # Run with empty tests list or a single test file to verify command construction does not fail
    tests, json_path = run_pytest(
        packages=["testless.config"],
        test_dirs=["tests/test_config.py"],
        coverage_dir=str(cov_dir),
    )
    assert json_path.exists()
    assert isinstance(tests, list)


def test_endpoint_inventory_ignores_vendor_dirs(tmp_path: Path):
    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    vendor_file = venv_dir / "routes.py"
    vendor_file.write_text(
        textwrap.dedent("""\
            @app.route('/vendor_endpoint')
            def vendor():
                pass
        """)
    )
    inv = EndpointInventory()
    inv.scan_directory(tmp_path)
    paths = {e.path for e in inv.endpoints}
    assert "/vendor_endpoint" not in paths


def test_fixture_index_ignores_vendor_dirs(tmp_path: Path):
    node_dir = tmp_path / "node_modules" / "sub"
    node_dir.mkdir(parents=True)
    vendor_file = node_dir / "conftest.py"
    vendor_file.write_text(
        textwrap.dedent("""\
            import pytest

            @pytest.fixture
            def vendor_fixture():
                return 42
        """)
    )
    index = FixtureIndex()
    index.scan_directory(tmp_path)
    assert "vendor_fixture" not in index.all_defined_fixtures()


def test_resolve_python_executable(tmp_path: Path, monkeypatch):
    from testless.collect.pytest_runner import resolve_python_executable

    # Custom python provided and exists
    dummy_py = tmp_path / "custom_python"
    dummy_py.write_text("#!/bin/sh\n")
    assert resolve_python_executable(str(dummy_py)) == str(dummy_py.resolve())

    # VIRTUAL_ENV set
    fake_venv = tmp_path / "fake_env"
    fake_bin = fake_venv / "bin"
    fake_bin.mkdir(parents=True)
    fake_py = fake_bin / "python"
    fake_py.write_text("#!/bin/sh\n")
    monkeypatch.setenv("VIRTUAL_ENV", str(fake_venv))
    assert resolve_python_executable() == str(fake_py.resolve())


