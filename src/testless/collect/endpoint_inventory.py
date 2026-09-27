"""Discover HTTP endpoints and service modules for missing-test analysis."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EndpointInfo:
    path: str
    method: str
    module: str
    handler: str
    line: int = 0


@dataclass
class ServiceInfo:
    module: str
    file: str
    has_sql: bool = False
    has_http_client: bool = False
    has_retry: bool = False


class EndpointInventory:
    """Scan source files to discover HTTP endpoints and service modules."""

    # Common HTTP method decorator patterns (Flask, FastAPI, Django)
    _ROUTE_PATTERN = re.compile(
        r'(route|get|post|put|patch|delete|head|options)\s*\(\s*["\']([^"\']+)',
        re.IGNORECASE,
    )

    _SQL_INDICATORS = {"execute", "query", "cursor", "session", "select", "insert", "update"}
    _HTTP_CLIENT_INDICATORS = {"requests", "httpx", "aiohttp", "urllib", "ClientSession"}
    _RETRY_INDICATORS = {"retry", "backoff", "tenacity", "Retry"}

    def __init__(self) -> None:
        self.endpoints: list[EndpointInfo] = []
        self.services: list[ServiceInfo] = []

    def scan_directory(self, directory: str | Path) -> None:
        """Recursively scan Python source files."""
        root = Path(directory)
        for py_file in root.rglob("*.py"):
            # Skip test files
            if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
                continue
            self._scan_file(py_file)

    def _scan_file(self, path: Path) -> None:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            return

        module_name = ".".join(path.with_suffix("").parts)
        service = ServiceInfo(module=module_name, file=str(path))

        # Check imports for SQL/HTTP/retry indicators
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name in self._HTTP_CLIENT_INDICATORS:
                        service.has_http_client = True
                    if name in self._RETRY_INDICATORS:
                        service.has_retry = True
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod in self._HTTP_CLIENT_INDICATORS:
                        service.has_http_client = True
                    if root_mod in self._RETRY_INDICATORS:
                        service.has_retry = True

            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Look for route decorators
                for dec in node.decorator_list:
                    dec_src = ast.unparse(dec)
                    m = self._ROUTE_PATTERN.search(dec_src)
                    if m:
                        method = m.group(1).upper()
                        ep_path = m.group(2)
                        self.endpoints.append(
                            EndpointInfo(
                                path=ep_path,
                                method=method,
                                module=module_name,
                                handler=node.name,
                                line=node.lineno,
                            )
                        )

            elif isinstance(node, ast.Attribute):
                if node.attr in self._SQL_INDICATORS:
                    service.has_sql = True

        # Only record as a service if it has interesting characteristics
        if service.has_sql or service.has_http_client or service.has_retry or self.endpoints:
            self.services.append(service)
