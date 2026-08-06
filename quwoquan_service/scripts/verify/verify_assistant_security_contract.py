#!/usr/bin/env python3
"""Verify every non-public Assistant route requires authenticated access."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "assistant-service"
    / "contracts"
)

def route_auth_mode(route: dict) -> str:
    security = route.get("security")
    if isinstance(security, dict):
        return str(security.get("auth_mode") or "").strip().lower()
    return ""


def is_explicit_public_catalog_route(route: dict) -> bool:
    if str(route.get("actor") or "").strip().lower() != "none":
        return False
    privacy = route.get("privacy")
    if not isinstance(privacy, dict):
        return False
    request_classification = str(
        privacy.get("request_classification") or ""
    ).strip().upper()
    response_classification = str(
        privacy.get("response_classification") or ""
    ).strip().upper()
    return (
        request_classification == "PUBLIC"
        and response_classification == "PUBLIC"
    )


def main() -> int:
    by_operation: dict[str, dict] = {}
    failures: list[str] = []
    service_paths = sorted(SERVICE_DIR.glob("*/*/operations.yaml"))
    if not service_paths:
        print(f"FAIL: {SERVICE_DIR} has no service metadata", file=sys.stderr)
        return 1
    for service_path in service_paths:
        data = yaml.safe_load(service_path.read_text(encoding="utf-8"))
        routes = data.get("api_routes") if isinstance(data, dict) else None
        if not isinstance(routes, list):
            failures.append(f"{service_path}: missing api_routes")
            continue
        for route in routes:
            if not isinstance(route, dict) or not route.get("operation"):
                continue
            operation = str(route["operation"])
            if operation in by_operation:
                failures.append(f"{operation}: duplicate metadata route")
                continue
            by_operation[operation] = route
    for operation, route in sorted(by_operation.items()):
        if is_explicit_public_catalog_route(route):
            continue
        mode = route_auth_mode(route)
        if mode != "required":
            failures.append(f"{operation}: auth_mode={mode!r}, want 'required'")
    if failures:
        print(
            "verify_assistant_security_contract: FAIL\n  " + "\n  ".join(failures),
            file=sys.stderr,
        )
        return 1
    print("verify_assistant_security_contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
