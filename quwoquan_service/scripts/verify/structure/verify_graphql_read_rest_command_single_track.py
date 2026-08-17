#!/usr/bin/env python3
"""报告 GraphQL read / REST command 结构违规与 legacy read 迁移义务。"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SERVICE_ROOT = Path(__file__).resolve().parents[3]
GRAPHQL_ENDPOINT_PATH = "/graphql"
CANONICAL_OPERATION_TYPES = frozenset({"command", "query", "session"})
APP_PUBLIC_QUERY_PRINCIPALS = frozenset({"public", "account", "persona", "device"})
OPERATOR_QUERY_PRINCIPALS = frozenset({"admin", "operator"})
FULL_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


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


def _migration_identity(obligation: dict[str, Any]) -> tuple[str, str, str, str]:
    values = (
        obligation.get("sourcePath"),
        obligation.get("operation"),
        obligation.get("method"),
        obligation.get("path"),
    )
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("migration obligation identity must contain sourcePath/operation/method/path")
    return values  # type: ignore[return-value]


def _identity_document(identity: tuple[str, str, str, str]) -> dict[str, str]:
    return {
        "sourcePath": identity[0],
        "operation": identity[1],
        "method": identity[2],
        "path": identity[3],
    }


def _build_worktree_report(service_root: Path) -> dict[str, Any]:
    service_root = service_root.resolve()
    files = _operations_files(service_root)
    issues: list[dict[str, Any]] = []
    migration_obligations: list[dict[str, Any]] = []
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
            for route_issue in route_issues:
                if route_issue["code"] == "GRAPHQL_READ_REST_COMMAND.APP_PUBLIC_REST_QUERY":
                    migration_obligations.append(route_issue)
                else:
                    issues.append(route_issue)
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
    migration_obligations.sort(key=_issue_sort_key)
    summary = {
        "operationsFiles": len(files),
        **counters,
        "structuralIssues": len(issues),
        "migrationObligations": len(migration_obligations),
        "migrationRegressions": 0,
        "issues": len(issues),
    }
    return {
        "schemaVersion": 2,
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
        "migrationBaseline": None,
        "migrationObligations": migration_obligations,
        "migrationRegressions": [],
        "issues": issues,
    }


def _run_git(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise ValueError(detail)
    return completed.stdout.strip()


def _resolve_immutable_commit(repo_root: Path, value: str, label: str) -> str:
    if FULL_GIT_SHA_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be an immutable full Git commit SHA")
    resolved = _run_git(repo_root, "rev-parse", "--verify", f"{value}^{{commit}}")
    if FULL_GIT_SHA_RE.fullmatch(resolved) is None or resolved != value:
        raise ValueError(f"{label} did not resolve to the exact supplied commit SHA")
    return resolved


def _materialize_service_tree(service_root: Path, commit_sha: str) -> tempfile.TemporaryDirectory[str]:
    repo_root = Path(_run_git(service_root, "rev-parse", "--show-toplevel")).resolve()
    try:
        service_prefix = service_root.resolve().relative_to(repo_root).as_posix()
    except ValueError as error:
        raise ValueError("service root must be inside the Git repository") from error
    prefixes = (
        f"{service_prefix}/services",
        f"{service_prefix}/control-plane",
        f"{service_prefix}/contracts/metadata/_schemas/operations.schema.json",
    )
    temporary: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
    target_root = Path(temporary.name) / "quwoquan_service"
    prefix_with_separator = f"{service_prefix}/"
    listed = _run_git(
        repo_root,
        "ls-tree",
        "-r",
        "--name-only",
        commit_sha,
        "--",
        *prefixes,
    )
    schema_path = prefixes[2]
    archive_paths = [
        path
        for path in listed.splitlines()
        if path == schema_path or path.endswith("/operations.yaml")
    ]
    if not archive_paths:
        temporary.cleanup()
        raise ValueError(f"{commit_sha} contains no service operations authoring tree")
    completed = subprocess.run(
        ["git", "archive", "--format=tar", commit_sha, "--", *archive_paths],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        temporary.cleanup()
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(detail or f"cannot archive service tree at {commit_sha}")
    extracted_files = 0
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            repository_path = member.name
            if not repository_path.startswith(prefix_with_separator):
                temporary.cleanup()
                raise ValueError("Git tree path escaped the service root")
            relative = Path(repository_path.removeprefix(prefix_with_separator))
            if relative.is_absolute() or ".." in relative.parts:
                temporary.cleanup()
                raise ValueError("Git tree path is unsafe")
            source = archive.extractfile(member)
            if source is None:
                temporary.cleanup()
                raise ValueError(f"cannot read archived Git tree path {repository_path}")
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
            extracted_files += 1
    if extracted_files == 0:
        temporary.cleanup()
        raise ValueError(f"{commit_sha} contains no service operations authoring tree")
    return temporary


def _report_at_commit(service_root: Path, commit_sha: str) -> dict[str, Any]:
    temporary = _materialize_service_tree(service_root, commit_sha)
    try:
        return _build_worktree_report(Path(temporary.name) / "quwoquan_service")
    finally:
        temporary.cleanup()


def build_report(
    service_root: Path,
    *,
    migration_base_sha: str | None = None,
    migration_candidate_sha: str | None = None,
) -> dict[str, Any]:
    service_root = service_root.resolve()
    report = _build_worktree_report(service_root)
    if migration_candidate_sha is not None and migration_base_sha is None:
        raise ValueError("migration candidate SHA requires a migration base SHA")
    if migration_base_sha is None:
        return report

    repo_root = Path(_run_git(service_root, "rev-parse", "--show-toplevel")).resolve()
    base_sha = _resolve_immutable_commit(repo_root, migration_base_sha, "migration base SHA")
    if migration_candidate_sha is None:
        candidate_sha = _run_git(repo_root, "rev-parse", "HEAD")
        candidate_report = report
        candidate_source = "worktree"
    else:
        candidate_sha = _resolve_immutable_commit(
            repo_root,
            migration_candidate_sha,
            "migration candidate SHA",
        )
        candidate_report = _report_at_commit(service_root, candidate_sha)
        candidate_source = "git_commit"
    report = candidate_report
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, candidate_sha],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        raise ValueError("migration base SHA must be an ancestor of the candidate SHA")

    base_report = _report_at_commit(service_root, base_sha)
    base_identities = {
        _migration_identity(item) for item in base_report["migrationObligations"]
    }
    candidate_by_identity = {
        _migration_identity(item): item
        for item in candidate_report["migrationObligations"]
    }
    regressions = []
    for identity in sorted(set(candidate_by_identity) - base_identities):
        regressions.append(
            {
                "code": "GRAPHQL_READ_REST_COMMAND.MIGRATION_OBLIGATION_ADDED_OR_REIDENTIFIED",
                "identity": _identity_document(identity),
                "message": (
                    "candidate introduced a new App/public REST query identity; legacy migration "
                    "obligations may only decrease"
                ),
            }
        )

    report["migrationBaseline"] = {
        "baseCommitSha": base_sha,
        "baseObligationCount": len(base_identities),
        "candidateCommitSha": candidate_sha,
        "candidateSource": candidate_source,
        "candidateObligationCount": len(candidate_by_identity),
    }
    report["migrationRegressions"] = regressions
    report["summary"]["migrationRegressions"] = len(regressions)
    return report


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
        "--migration-base-sha",
        help=(
            "immutable full Git SHA whose App/public REST query identity set is the migration "
            "ratchet base"
        ),
    )
    parser.add_argument(
        "--migration-candidate-sha",
        help=(
            "optional immutable full Git SHA to compare; omitted means the current worktree"
        ),
    )
    parser.add_argument(
        "--require-structural-zero",
        action="store_true",
        help="return non-zero when structural GraphQL/REST transport issues exist",
    )
    parser.add_argument(
        "--require-no-migration-growth",
        action="store_true",
        help="return non-zero when the candidate adds or re-identifies a migration obligation",
    )
    parser.add_argument(
        "--require-zero",
        action="store_true",
        help=(
            "release-cutover report predicate: require both structural issues and all legacy "
            "migration obligations to be zero; hosted/minimum-build/zero-call lifecycle evidence "
            "must be verified by the release caller"
        ),
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="print gate-relevant summary, issues, and regressions without the full obligation list",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.require_no_migration_growth and not args.migration_base_sha:
        print(
            "GATE_BLOCK: --require-no-migration-growth requires --migration-base-sha",
            file=sys.stderr,
        )
        return 2
    try:
        report = build_report(
            args.service_root,
            migration_base_sha=args.migration_base_sha,
            migration_candidate_sha=args.migration_candidate_sha,
        )
    except ValueError as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    rendered = report
    if args.summary_only:
        rendered = {
            "schemaVersion": report["schemaVersion"],
            "summary": report["summary"],
            "migrationBaseline": report["migrationBaseline"],
            "migrationRegressions": report["migrationRegressions"],
            "issues": report["issues"],
        }
    print(render_report(rendered), end="")
    if args.require_structural_zero and report["summary"]["structuralIssues"] != 0:
        return 1
    if args.require_no_migration_growth and report["summary"]["migrationRegressions"] != 0:
        return 1
    if args.require_zero and (
        report["summary"]["structuralIssues"] != 0
        or report["summary"]["migrationObligations"] != 0
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
