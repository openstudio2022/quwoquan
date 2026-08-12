#!/usr/bin/env python3
"""报告业务 REST query，并可作为 GraphQL read / REST command 硬门执行。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SERVICE_ROOT = Path(__file__).resolve().parents[3]
GRAPHQL_ENDPOINT_PATH = "/graphql"
CANONICAL_OPERATION_TYPES = frozenset({"command", "query", "session"})
APP_PUBLIC_QUERY_PRINCIPALS = frozenset({"public", "account", "persona", "device"})
OPERATOR_QUERY_PRINCIPALS = frozenset({"admin", "operator"})


def _allowed_non_business_transport_roles(service_root: Path) -> frozenset[str]:
    schema_path = (
        service_root / "contracts/metadata/_schemas/operations.schema.json"
    )
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        values = schema["properties"]["api_routes"]["items"]["properties"][
            "transport_role"
        ]["enum"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(
            f"cannot derive transport_role closed set from {schema_path}: {error}"
        ) from error
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not value for value in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError(
            f"transport_role enum in {schema_path} must be a non-empty unique string list"
        )
    return frozenset(values)


def _operations_files(service_root: Path) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for base in (service_root / "services", service_root / "control-plane"):
        if not base.is_dir():
            continue
        paths.update(path for path in base.glob("*/contracts/**/operations.yaml") if path.is_file())
    return tuple(sorted(paths, key=lambda item: item.as_posix()))


def _relative(service_root: Path, path: Path) -> str:
    try:
        return path.relative_to(service_root).as_posix()
    except ValueError:
        return path.as_posix()


def _issue(
    *,
    code: str,
    source_path: str,
    route_index: int | None,
    operation: str | None,
    method: str | None,
    path: str | None,
    operation_type: str | None,
    transport_role: str | None,
    message: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "sourcePath": source_path,
        "routeIndex": route_index,
        "operation": operation,
        "method": method,
        "path": path,
        "operationType": operation_type,
        "transportRole": transport_role,
        "message": message,
    }


def _route_identity(route: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    operation = route.get("operation")
    method = route.get("method")
    path = route.get("path")
    return (
        operation if isinstance(operation, str) else None,
        method if isinstance(method, str) else None,
        path if isinstance(path, str) else None,
    )


def _route_operation_type(route: dict[str, Any]) -> str | None:
    application = route.get("application")
    if not isinstance(application, dict):
        return None
    kind = application.get("kind")
    return kind if isinstance(kind, str) else None


def _route_transport_role(route: dict[str, Any]) -> str | None:
    value = route.get("transport_role")
    return value if isinstance(value, str) else None


def _authorization(route: dict[str, Any]) -> dict[str, Any]:
    value = route.get("authorization")
    return value if isinstance(value, dict) else {}


def _security(route: dict[str, Any]) -> dict[str, Any]:
    value = route.get("security")
    return value if isinstance(value, dict) else {}


def _non_empty_unique_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
        and len(set(value)) == len(value)
    )


def _inspect_route(
    source_path: str,
    route_index: int,
    route: Any,
    allowed_transport_roles: frozenset[str],
) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(route, dict):
        return (
            [
                _issue(
                    code="GRAPHQL_READ_REST_COMMAND.ROUTE_INVALID",
                    source_path=source_path,
                    route_index=route_index,
                    operation=None,
                    method=None,
                    path=None,
                    operation_type=None,
                    transport_role=None,
                    message="api_routes entry must be an object",
                )
            ],
            None,
        )

    operation, method, path = _route_identity(route)
    operation_type = _route_operation_type(route)
    route_transport = route.get("transport")
    if not isinstance(route_transport, str):
        route_transport = "json"
    transport_value = route.get("transport_role")
    transport_role = _route_transport_role(route)
    issues: list[dict[str, Any]] = []
    transport_role_matches = not (
        transport_role == "sse" and route_transport != "sse"
    )

    if transport_value is not None and transport_role not in allowed_transport_roles:
        issues.append(
            _issue(
                code="GRAPHQL_READ_REST_COMMAND.TRANSPORT_ROLE_UNKNOWN",
                source_path=source_path,
                route_index=route_index,
                operation=operation,
                method=method,
                path=path,
                operation_type=operation_type,
                transport_role=transport_role,
                message=(
                    "transport_role must be an explicit canonical non-business transport role; "
                    "route paths and HTTP methods never imply an exception"
                ),
            )
        )

    if not transport_role_matches:
        issues.append(
            _issue(
                code="GRAPHQL_READ_REST_COMMAND.TRANSPORT_ROLE_MISMATCH",
                source_path=source_path,
                route_index=route_index,
                operation=operation,
                method=method,
                path=path,
                operation_type=operation_type,
                transport_role=transport_role,
                message="transport_role sse requires the canonical sse transport",
            )
        )

    if path == GRAPHQL_ENDPOINT_PATH:
        if operation_type in {"command", "mutation"}:
            issues.append(
                _issue(
                    code="GRAPHQL_READ_REST_COMMAND.GRAPHQL_MUTATION_FORBIDDEN",
                    source_path=source_path,
                    route_index=route_index,
                    operation=operation,
                    method=method,
                    path=path,
                    operation_type=operation_type,
                    transport_role=transport_role,
                    message="the GraphQL endpoint is query-only; state changes require REST command",
                )
            )
            return issues, "graphql_forbidden"
        if operation_type != "query":
            issues.append(
                _issue(
                    code="GRAPHQL_READ_REST_COMMAND.OPERATION_TYPE_UNKNOWN",
                    source_path=source_path,
                    route_index=route_index,
                    operation=operation,
                    method=method,
                    path=path,
                    operation_type=operation_type,
                    transport_role=transport_role,
                    message="GraphQL authoring operationType must be query",
                )
            )
            return issues, "unknown"
        return issues, "graphql_query"

    if operation_type not in CANONICAL_OPERATION_TYPES:
        issues.append(
            _issue(
                code="GRAPHQL_READ_REST_COMMAND.OPERATION_TYPE_UNKNOWN",
                source_path=source_path,
                route_index=route_index,
                operation=operation,
                method=method,
                path=path,
                operation_type=operation_type,
                transport_role=transport_role,
                message="application.kind must be command, query, or session",
            )
        )
        return issues, "unknown"

    if transport_role in allowed_transport_roles and transport_role_matches:
        return issues, "explicit_transport"

    if operation_type == "query":
        authorization = _authorization(route)
        principal = authorization.get("principal")
        security = _security(route)
        if principal == "service":
            if not _non_empty_unique_strings(authorization.get("scopes")):
                issues.append(
                    _issue(
                        code="GRAPHQL_READ_REST_COMMAND.TYPED_OWNER_SCOPE_REQUIRED",
                        source_path=source_path,
                        route_index=route_index,
                        operation=operation,
                        method=method,
                        path=path,
                        operation_type=operation_type,
                        transport_role=transport_role,
                        message=(
                            "typed owner query requires at least one explicit service scope; "
                            "a service principal alone is not an authorization boundary"
                        ),
                    )
                )
            if not (
                security.get("auth_mode") == "required"
                and security.get("principal") == "service"
                and security.get("visibility") == "internal"
            ):
                issues.append(
                    _issue(
                        code="GRAPHQL_READ_REST_COMMAND.TYPED_OWNER_SECURITY_REQUIRED",
                        source_path=source_path,
                        route_index=route_index,
                        operation=operation,
                        method=method,
                        path=path,
                        operation_type=operation_type,
                        transport_role=transport_role,
                        message=(
                            "typed owner query requires required service authentication and "
                            "internal visibility before owner execution"
                        ),
                    )
                )
            if issues:
                return issues, "typed_owner_query_invalid"
            return issues, "typed_owner_query"

        if principal in OPERATOR_QUERY_PRINCIPALS:
            if not (
                _non_empty_unique_strings(authorization.get("scopes"))
                and security.get("auth_mode") == "required"
            ):
                issues.append(
                    _issue(
                        code="GRAPHQL_READ_REST_COMMAND.OPERATOR_CONTROL_PLANE_SECURITY_REQUIRED",
                        source_path=source_path,
                        route_index=route_index,
                        operation=operation,
                        method=method,
                        path=path,
                        operation_type=operation_type,
                        transport_role=transport_role,
                        message=(
                            "operator control-plane query requires required authentication and "
                            "at least one explicit operator scope"
                        ),
                    )
                )
                return issues, "operator_control_plane_query_invalid"
            return issues, "operator_control_plane_query"

        if principal in APP_PUBLIC_QUERY_PRINCIPALS:
            issues.append(
                _issue(
                    code="GRAPHQL_READ_REST_COMMAND.APP_PUBLIC_REST_QUERY",
                    source_path=source_path,
                    route_index=route_index,
                    operation=operation,
                    method=method,
                    path=path,
                    operation_type=operation_type,
                    transport_role=transport_role,
                    message=(
                        "App/public business query must migrate to a signed persisted GraphQL "
                        "Query Slice before the legacy REST route can retire"
                    ),
                )
            )
            return issues, "app_public_legacy_rest_query"

        issues.append(
            _issue(
                code="GRAPHQL_READ_REST_COMMAND.QUERY_AUDIENCE_UNCLASSIFIED",
                source_path=source_path,
                route_index=route_index,
                operation=operation,
                method=method,
                path=path,
                operation_type=operation_type,
                transport_role=transport_role,
                message=(
                    "business query audience cannot be derived from canonical authorization; "
                    "paths and HTTP methods never imply a legal read transport"
                ),
            )
        )
        return issues, "unclassified_rest_query"

    return issues, f"rest_{operation_type}"


def _issue_sort_key(issue: dict[str, Any]) -> tuple[Any, ...]:
    route_index = issue.get("routeIndex")
    return (
        issue.get("sourcePath") or "",
        route_index if isinstance(route_index, int) else -1,
        issue.get("code") or "",
        issue.get("operation") or "",
    )


def build_report(service_root: Path) -> dict[str, Any]:
    service_root = service_root.resolve()
    files = _operations_files(service_root)
    issues: list[dict[str, Any]] = []
    try:
        allowed_transport_roles = _allowed_non_business_transport_roles(service_root)
    except ValueError as error:
        allowed_transport_roles = frozenset()
        issues.append(
            _issue(
                code="GRAPHQL_READ_REST_COMMAND.TRANSPORT_ROLE_SCHEMA_INVALID",
                source_path="contracts/metadata/_schemas/operations.schema.json",
                route_index=None,
                operation=None,
                method=None,
                path=None,
                operation_type=None,
                transport_role=None,
                message=str(error),
            )
        )
    counters = {
        "routes": 0,
        "graphqlQueryRoutes": 0,
        "restCommandRoutes": 0,
        "restSessionRoutes": 0,
        "restQueryRoutes": 0,
        "appPublicLegacyRestQueryRoutes": 0,
        "typedOwnerQueryRoutes": 0,
        "invalidTypedOwnerQueryRoutes": 0,
        "operatorControlPlaneQueryRoutes": 0,
        "invalidOperatorControlPlaneQueryRoutes": 0,
        "unclassifiedRestQueryRoutes": 0,
        "explicitNonBusinessTransportRoutes": 0,
    }
    query_route_classifications: list[dict[str, Any]] = []

    if not service_root.is_dir():
        issues.append(
            _issue(
                code="GRAPHQL_READ_REST_COMMAND.SERVICE_ROOT_MISSING",
                source_path=service_root.as_posix(),
                route_index=None,
                operation=None,
                method=None,
                path=None,
                operation_type=None,
                transport_role=None,
                message="service root does not exist",
            )
        )
    elif not files:
        issues.append(
            _issue(
                code="GRAPHQL_READ_REST_COMMAND.OPERATIONS_SCAN_EMPTY",
                source_path=service_root.as_posix(),
                route_index=None,
                operation=None,
                method=None,
                path=None,
                operation_type=None,
                transport_role=None,
                message="no service or control-plane operations.yaml files were discovered",
            )
        )

    for operations_path in files:
        source_path = _relative(service_root, operations_path)
        try:
            payload = yaml.safe_load(operations_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            issues.append(
                _issue(
                    code="GRAPHQL_READ_REST_COMMAND.CONTRACT_LOAD_FAILED",
                    source_path=source_path,
                    route_index=None,
                    operation=None,
                    method=None,
                    path=None,
                    operation_type=None,
                    transport_role=None,
                    message=f"cannot load operations authoring contract: {exc}",
                )
            )
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("api_routes"), list):
            issues.append(
                _issue(
                    code="GRAPHQL_READ_REST_COMMAND.API_ROUTES_INVALID",
                    source_path=source_path,
                    route_index=None,
                    operation=None,
                    method=None,
                    path=None,
                    operation_type=None,
                    transport_role=None,
                    message="operations authoring contract must declare api_routes as an array",
                )
            )
            continue

        for route_index, route in enumerate(payload["api_routes"]):
            counters["routes"] += 1
            route_issues, classification = _inspect_route(
                source_path,
                route_index,
                route,
                allowed_transport_roles,
            )
            issues.extend(route_issues)
            if classification == "graphql_query":
                counters["graphqlQueryRoutes"] += 1
            elif classification == "rest_command":
                counters["restCommandRoutes"] += 1
            elif classification == "rest_session":
                counters["restSessionRoutes"] += 1
            elif classification in {
                "app_public_legacy_rest_query",
                "typed_owner_query",
                "typed_owner_query_invalid",
                "operator_control_plane_query",
                "operator_control_plane_query_invalid",
                "unclassified_rest_query",
            }:
                counters["restQueryRoutes"] += 1
                counter_by_classification = {
                    "app_public_legacy_rest_query": "appPublicLegacyRestQueryRoutes",
                    "typed_owner_query": "typedOwnerQueryRoutes",
                    "typed_owner_query_invalid": "invalidTypedOwnerQueryRoutes",
                    "operator_control_plane_query": "operatorControlPlaneQueryRoutes",
                    "operator_control_plane_query_invalid": "invalidOperatorControlPlaneQueryRoutes",
                    "unclassified_rest_query": "unclassifiedRestQueryRoutes",
                }
                counters[counter_by_classification[classification]] += 1
                operation, method, path = _route_identity(route)
                query_route_classifications.append(
                    {
                        "sourcePath": source_path,
                        "routeIndex": route_index,
                        "operation": operation,
                        "method": method,
                        "path": path,
                        "audience": classification.removesuffix("_invalid"),
                        "valid": not classification.endswith("_invalid")
                        and classification != "unclassified_rest_query",
                    }
                )
            elif classification == "explicit_transport":
                counters["explicitNonBusinessTransportRoutes"] += 1

    issues.sort(key=_issue_sort_key)
    summary = {
        "operationsFiles": len(files),
        **counters,
        "issues": len(issues),
    }
    return {
        "schemaVersion": 1,
        "policy": {
            "appPublicBusinessReadTransport": "persisted_graphql_query",
            "typedOwnerReadTransport": "service_principal_owner_query",
            "operatorControlPlaneReadTransport": "scoped_operator_query",
            "businessWriteTransport": "rest_command",
            "graphqlMutationAllowed": False,
            "allowedNonBusinessTransportRoles": sorted(
                allowed_transport_roles
            ),
        },
        "summary": summary,
        "queryRouteClassifications": query_route_classifications,
        "issues": issues,
    }


def render_report(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report REST business query routes and optionally require the GraphQL read / "
            "REST command single track to be violation-free."
        )
    )
    parser.add_argument(
        "--service-root",
        type=Path,
        default=DEFAULT_SERVICE_ROOT,
        help="quwoquan_service root (defaults to the root containing this verifier)",
    )
    parser.add_argument(
        "--require-zero",
        action="store_true",
        help="return non-zero when the deterministic report contains any issue",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_report(args.service_root)
    print(render_report(report), end="")
    if args.require_zero and report["summary"]["issues"] != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
