"""Suggest missing tests based on endpoints, services, and modules."""

from __future__ import annotations

from testless.collect.endpoint_inventory import EndpointInfo, ServiceInfo
from testless.models.findings import MissingTestFinding, TestMeta

# Endpoint paths that should always have smoke test coverage
_CRITICAL_PATHS = {"/health", "/login", "/logout", "/search", "/checkout", "/billing", "/register"}


def _has_smoke_test(endpoint: EndpointInfo, tests: list[TestMeta]) -> bool:
    """Heuristic: check if any test name references the endpoint path."""
    slug = endpoint.path.strip("/").replace("/", "_").replace("-", "_")
    for test in tests:
        if slug.lower() in test.name.lower() or slug.lower() in test.file.lower():
            return True
    return False


def _has_service_test(service: ServiceInfo, tests: list[TestMeta]) -> bool:
    """Heuristic: check if any test imports or references the service module."""
    module_slug = service.module.split(".")[-1]
    for test in tests:
        if module_slug.lower() in test.name.lower() or module_slug.lower() in test.file.lower():
            return True
    return False


def find_missing_tests(
    tests: list[TestMeta],
    endpoints: list[EndpointInfo],
    services: list[ServiceInfo],
) -> list[MissingTestFinding]:
    """Return suggested missing tests based on inventory."""
    findings: list[MissingTestFinding] = []

    for endpoint in endpoints:
        if not _has_smoke_test(endpoint, tests):
            priority = "high" if endpoint.path in _CRITICAL_PATHS else "medium"
            findings.append(
                MissingTestFinding(
                    target=f"{endpoint.method} {endpoint.path}",
                    test_type="smoke",
                    description=(
                        f"No smoke test found for {endpoint.method} {endpoint.path} "
                        f"(handler: {endpoint.handler}). "
                        "Add tests for 2xx, 4xx, and 5xx responses."
                    ),
                    priority=priority,
                    suggested_file=f"tests/smoke/test_{endpoint.handler}.py",
                )
            )

    for service in services:
        if not _has_service_test(service, tests):
            if service.has_sql:
                findings.append(
                    MissingTestFinding(
                        target=service.module,
                        test_type="testql",
                        description=(
                            f"Service {service.module} uses SQL but has no detected tests. "
                            "Consider adding TestQL contract tests for critical queries."
                        ),
                        priority="high",
                        suggested_file=f"tests/service/test_{service.module.split('.')[-1]}.py",
                    )
                )
            if service.has_http_client:
                findings.append(
                    MissingTestFinding(
                        target=service.module,
                        test_type="contract",
                        description=(
                            f"Service {service.module} makes HTTP calls but has no contract tests. "
                            "Add service contract tests for timeout and dependency failure scenarios."
                        ),
                        priority="medium",
                        suggested_file=f"tests/service/test_{service.module.split('.')[-1]}_contract.py",
                    )
                )
            if service.has_retry:
                findings.append(
                    MissingTestFinding(
                        target=service.module,
                        test_type="resilience",
                        description=(
                            f"Service {service.module} uses retry/backoff but has no resilience tests. "
                            "Add tests for circuit-breaker and retry-exhaustion scenarios."
                        ),
                        priority="medium",
                        suggested_file=f"tests/service/test_{service.module.split('.')[-1]}_resilience.py",
                    )
                )

    return findings
