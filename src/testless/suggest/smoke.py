"""Generate smoke test templates for discovered endpoints."""

from __future__ import annotations

from testless.collect.endpoint_inventory import EndpointInfo

_SMOKE_TEMPLATE = '''\
"""Smoke tests for {method} {path}."""
import pytest


@pytest.mark.smoke
def test_{handler}_success(client):
    """Happy-path smoke test: expect 2xx."""
    response = client.{method_lower}("{path}")
    assert response.status_code < 300


@pytest.mark.smoke
def test_{handler}_not_found(client):
    """Smoke test: missing resource returns 4xx."""
    response = client.{method_lower}("{path}/__nonexistent__")
    assert 400 <= response.status_code < 500


@pytest.mark.smoke
def test_{handler}_server_error(client, monkeypatch):
    """Smoke test: simulate 5xx by patching the handler."""
    # TODO: monkeypatch the service layer to raise an exception
    pass
'''


def render_smoke_test(endpoint: EndpointInfo) -> str:
    """Return a smoke test template string for the given endpoint."""
    return _SMOKE_TEMPLATE.format(
        method=endpoint.method,
        method_lower=endpoint.method.lower(),
        path=endpoint.path,
        handler=endpoint.handler,
    )
