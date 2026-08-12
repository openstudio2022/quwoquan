#!/usr/bin/env python3
"""GraphQL read / REST command single-track verifier contract tests."""

# spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[7]
VERIFIER_PATH = (
    REPO_ROOT
    / "quwoquan_service/scripts/verify/structure/verify_graphql_read_rest_command_single_track.py"
)
OPERATIONS_SCHEMA_PATH = (
    REPO_ROOT / "quwoquan_service/contracts/metadata/_schemas/operations.schema.json"
)


def _load_verifier():
    spec = importlib.util.spec_from_file_location("graphql_rest_single_track", VERIFIER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier: {VERIFIER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _route(
    operation: str,
    kind: str,
    path: str,
    *,
    method: str = "GET",
    transport_role: str | None = None,
    principal: str = "public",
    scopes: tuple[str, ...] = (),
    security_principal: str | None = None,
    visibility: str | None = None,
) -> dict[str, object]:
    route: dict[str, object] = {
        "method": method,
        "path": path,
        "operation": operation,
        "actor": "none",
        "application": {
            "kind": kind,
            "facet": "FixtureFacade",
            "method": "execute",
        },
        "authorization": {
            "principal": principal,
            "ownership_policy": "fixture_policy",
        },
        "security": {"auth_mode": "required"},
    }
    if scopes:
        route["authorization"]["scopes"] = list(scopes)
    if security_principal is not None:
        route["security"]["principal"] = security_principal
    if visibility is not None:
        route["security"]["visibility"] = visibility
    if transport_role is not None:
        route["transport_role"] = transport_role
    return route


class GraphQLReadRestCommandSingleTrackContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()

    def _service_root(self, files: dict[str, list[dict[str, object]]]) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "quwoquan_service"
        schema_target = root / "contracts/metadata/_schemas/operations.schema.json"
        schema_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OPERATIONS_SCHEMA_PATH, schema_target)
        for relative, routes in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"api_routes": routes}, ensure_ascii=False),
                encoding="utf-8",
            )
        return root

    def test_allows_graphql_query_rest_command_session_and_explicit_transport_roles(self) -> None:
        routes = [
            _route("ExecuteGraphQL", "query", "/graphql", method="POST"),
            _route("PublishPost", "command", "/content/posts:publish", method="POST"),
            _route("OpenEvents", "session", "/events", method="POST"),
        ]
        expected_roles = self.verifier.build_report(
            self._service_root({})
        )["policy"]["allowedNonBusinessTransportRoles"]
        for index, role in enumerate(expected_roles):
            route = _route(
                f"Transport{index}",
                "query",
                f"/explicit-transport-{index}",
                transport_role=role,
            )
            if role == "sse":
                route["transport"] = "sse"
            routes.append(route)
        root = self._service_root(
            {"services/example-service/contracts/example/object/operations.yaml": routes}
        )

        report = self.verifier.build_report(root)

        self.assertEqual(report["summary"]["operationsFiles"], 1)
        self.assertEqual(report["summary"]["routes"], len(routes))
        self.assertEqual(report["summary"]["issues"], 0)
        self.assertEqual(report["issues"], [])

    def test_classifies_typed_owner_and_operator_reads_without_routing_them_through_app_graphql(self) -> None:
        root = self._service_root(
            {
                "services/example-service/contracts/example/object/operations.yaml": [
                    _route(
                        "ReadOwnerSlice",
                        "query",
                        "/internal/example/owner-slice",
                        principal="service",
                        scopes=("example.owner.read",),
                        security_principal="service",
                        visibility="internal",
                    ),
                    _route(
                        "ReadOperatorSlice",
                        "query",
                        "/control-plane/example/summary",
                        principal="operator",
                        scopes=("ops.example.read",),
                    ),
                ]
            }
        )

        report = self.verifier.build_report(root)

        self.assertEqual(report["summary"]["typedOwnerQueryRoutes"], 1)
        self.assertEqual(report["summary"]["operatorControlPlaneQueryRoutes"], 1)
        self.assertEqual(report["summary"]["appPublicLegacyRestQueryRoutes"], 0)
        self.assertEqual(report["summary"]["issues"], 0)

    def test_rejects_untyped_owner_reads_and_keeps_app_public_rest_reads_blocking(self) -> None:
        root = self._service_root(
            {
                "services/example-service/contracts/example/object/operations.yaml": [
                    _route(
                        "OwnerWithoutScope",
                        "query",
                        "/internal/example/no-scope",
                        principal="service",
                        security_principal="service",
                        visibility="internal",
                    ),
                    _route(
                        "OwnerWithoutServiceSecurity",
                        "query",
                        "/internal/example/no-service-security",
                        principal="service",
                        scopes=("example.owner.read",),
                        visibility="internal",
                    ),
                    _route(
                        "LegacyAppRead",
                        "query",
                        "/example/detail",
                        principal="persona",
                    ),
                ]
            }
        )

        report = self.verifier.build_report(root)

        self.assertEqual(report["summary"]["typedOwnerQueryRoutes"], 0)
        self.assertEqual(report["summary"]["appPublicLegacyRestQueryRoutes"], 1)
        self.assertEqual(
            [issue["code"] for issue in report["issues"]],
            [
                "GRAPHQL_READ_REST_COMMAND.TYPED_OWNER_SCOPE_REQUIRED",
                "GRAPHQL_READ_REST_COMMAND.TYPED_OWNER_SECURITY_REQUIRED",
                "GRAPHQL_READ_REST_COMMAND.APP_PUBLIC_REST_QUERY",
            ],
        )

    def test_transport_roles_are_derived_from_operations_schema(self) -> None:
        root = self._service_root(
            {
                "services/example-service/contracts/example/object/operations.yaml": [
                    _route("Metrics", "query", "/metrics", transport_role="metrics"),
                    _route("Health", "query", "/healthz", transport_role="health"),
                ]
            }
        )
        schema_path = root / "contracts/metadata/_schemas/operations.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["properties"]["api_routes"]["items"]["properties"][
            "transport_role"
        ]["enum"] = ["metrics"]
        schema_path.write_text(
            json.dumps(schema, ensure_ascii=False),
            encoding="utf-8",
        )

        report = self.verifier.build_report(root)

        self.assertEqual(
            report["policy"]["allowedNonBusinessTransportRoles"], ["metrics"]
        )
        self.assertEqual(
            [issue["code"] for issue in report["issues"]],
            [
                "GRAPHQL_READ_REST_COMMAND.APP_PUBLIC_REST_QUERY",
                "GRAPHQL_READ_REST_COMMAND.TRANSPORT_ROLE_UNKNOWN",
            ],
        )

    def test_rejects_rest_query_graphql_mutation_unknown_kind_and_unknown_role(self) -> None:
        root = self._service_root(
            {
                "services/example-service/contracts/example/object/operations.yaml": [
                    _route("GetPost", "query", "/content/posts/{postId}"),
                    _route("HealthByPathOnly", "query", "/healthz"),
                    _route("ChangeViaGraphQL", "command", "/graphql", method="POST"),
                    _route("LiteralMutation", "mutation", "/graphql", method="POST"),
                    _route("UnknownKind", "stream", "/stream"),
                    _route(
                        "UnknownTransport",
                        "query",
                        "/callback",
                        transport_role="callback",
                    ),
                    _route(
                        "SseRoleOnJsonBusinessQuery",
                        "query",
                        "/content/events",
                        transport_role="sse",
                    ),
                ]
            }
        )

        report = self.verifier.build_report(root)
        codes = [issue["code"] for issue in report["issues"]]

        self.assertEqual(
            codes,
            [
                "GRAPHQL_READ_REST_COMMAND.APP_PUBLIC_REST_QUERY",
                "GRAPHQL_READ_REST_COMMAND.APP_PUBLIC_REST_QUERY",
                "GRAPHQL_READ_REST_COMMAND.GRAPHQL_MUTATION_FORBIDDEN",
                "GRAPHQL_READ_REST_COMMAND.GRAPHQL_MUTATION_FORBIDDEN",
                "GRAPHQL_READ_REST_COMMAND.OPERATION_TYPE_UNKNOWN",
                "GRAPHQL_READ_REST_COMMAND.APP_PUBLIC_REST_QUERY",
                "GRAPHQL_READ_REST_COMMAND.TRANSPORT_ROLE_UNKNOWN",
                "GRAPHQL_READ_REST_COMMAND.APP_PUBLIC_REST_QUERY",
                "GRAPHQL_READ_REST_COMMAND.TRANSPORT_ROLE_MISMATCH",
            ],
        )
        by_operation = {issue["operation"]: issue for issue in report["issues"]}
        self.assertEqual(by_operation["HealthByPathOnly"]["path"], "/healthz")
        self.assertIsNone(by_operation["HealthByPathOnly"]["transportRole"])
        self.assertIn("persisted GraphQL", by_operation["HealthByPathOnly"]["message"])

    def test_scans_services_and_control_plane_without_path_allowlists(self) -> None:
        root = self._service_root(
            {
                "services/a-service/contracts/a/item/operations.yaml": [
                    _route("ServiceQuery", "query", "/service/query")
                ],
                "control-plane/platform-ops/contracts/platform/item/operations.yaml": [
                    _route("ControlQuery", "query", "/control/query")
                ],
            }
        )

        report = self.verifier.build_report(root)

        self.assertEqual(report["summary"]["operationsFiles"], 2)
        self.assertEqual(report["summary"]["issues"], 2)
        self.assertEqual(
            [issue["operation"] for issue in report["issues"]],
            ["ControlQuery", "ServiceQuery"],
        )

    def test_report_is_deterministic_and_require_zero_controls_only_exit_status(self) -> None:
        root = self._service_root(
            {
                "services/z-service/contracts/z/item/operations.yaml": [
                    _route("ZQuery", "query", "/z")
                ],
                "services/a-service/contracts/a/item/operations.yaml": [
                    _route("AQuery", "query", "/a")
                ],
            }
        )
        first = self.verifier.render_report(self.verifier.build_report(root))
        second = self.verifier.render_report(self.verifier.build_report(root))
        self.assertEqual(first, second)

        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        report_only = subprocess.run(
            [sys.executable, "-B", str(VERIFIER_PATH), "--service-root", str(root)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        require_zero = subprocess.run(
            [
                sys.executable,
                "-B",
                str(VERIFIER_PATH),
                "--service-root",
                str(root),
                "--require-zero",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(report_only.returncode, 0, report_only.stderr)
        self.assertEqual(require_zero.returncode, 1, require_zero.stderr)
        self.assertEqual(report_only.stdout, require_zero.stdout)
        self.assertEqual(report_only.stdout, first)


if __name__ == "__main__":
    unittest.main()
