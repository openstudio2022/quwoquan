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
SERVICE_MAKEFILE_PATH = REPO_ROOT / "quwoquan_service/Makefile"


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

    def _git_service_root(self, routes: list[dict[str, object]]) -> tuple[Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository = Path(temporary.name) / "repository"
        root = repository / "quwoquan_service"
        schema_target = root / "contracts/metadata/_schemas/operations.schema.json"
        schema_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OPERATIONS_SCHEMA_PATH, schema_target)
        self._write_git_routes(root, routes)
        subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
        subprocess.run(
            ["git", "config", "user.email", "graphql-gate@example.invalid"],
            cwd=repository,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "GraphQL Gate Contract"],
            cwd=repository,
            check=True,
        )
        return repository, root

    @staticmethod
    def _write_git_routes(root: Path, routes: list[dict[str, object]]) -> None:
        path = root / "services/example-service/contracts/example/object/operations.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"api_routes": routes}, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _commit(repository: Path, message: str) -> str:
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", message],
            cwd=repository,
            check=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

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
            ],
        )
        self.assertEqual(
            [item["code"] for item in report["migrationObligations"]],
            ["GRAPHQL_READ_REST_COMMAND.APP_PUBLIC_REST_QUERY"],
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
            ["GRAPHQL_READ_REST_COMMAND.TRANSPORT_ROLE_UNKNOWN"],
        )
        self.assertEqual(report["summary"]["migrationObligations"], 1)

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
                "GRAPHQL_READ_REST_COMMAND.GRAPHQL_MUTATION_FORBIDDEN",
                "GRAPHQL_READ_REST_COMMAND.GRAPHQL_MUTATION_FORBIDDEN",
                "GRAPHQL_READ_REST_COMMAND.OPERATION_TYPE_UNKNOWN",
                "GRAPHQL_READ_REST_COMMAND.TRANSPORT_ROLE_UNKNOWN",
                "GRAPHQL_READ_REST_COMMAND.TRANSPORT_ROLE_MISMATCH",
            ],
        )
        self.assertEqual(
            [item["operation"] for item in report["migrationObligations"]],
            ["GetPost", "HealthByPathOnly", "UnknownTransport", "SseRoleOnJsonBusinessQuery"],
        )
        by_operation = {
            item["operation"]: item for item in report["migrationObligations"]
        }
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
        self.assertEqual(report["summary"]["issues"], 0)
        self.assertEqual(report["summary"]["migrationObligations"], 2)
        self.assertEqual(
            [item["operation"] for item in report["migrationObligations"]],
            ["ControlQuery", "ServiceQuery"],
        )

    def test_existing_legacy_identity_is_accepted_against_immutable_base(self) -> None:
        repository, root = self._git_service_root(
            [_route("LegacyQuery", "query", "/legacy")]
        )
        base_sha = self._commit(repository, "base")

        report = self.verifier.build_report(
            root,
            migration_base_sha=base_sha,
            migration_candidate_sha=base_sha,
        )

        self.assertEqual(report["summary"]["migrationObligations"], 1)
        self.assertEqual(report["summary"]["migrationRegressions"], 0)
        self.assertEqual(report["migrationRegressions"], [])

    def test_explicit_candidate_report_never_mixes_worktree_source_fields(self) -> None:
        repository, root = self._git_service_root(
            [_route("ExistingLegacy", "query", "/existing")]
        )
        base_sha = self._commit(repository, "base")
        schema_path = root / "contracts/metadata/_schemas/operations.schema.json"
        candidate_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        candidate_schema["properties"]["api_routes"]["items"]["properties"][
            "transport_role"
        ]["enum"] = ["health"]
        schema_path.write_text(
            json.dumps(candidate_schema, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_git_routes(
            root,
            [
                _route("ExistingLegacy", "query", "/existing"),
                _route("CandidateLegacy", "query", "/candidate"),
                _route("CandidateMutation", "command", "/graphql", method="POST"),
            ],
        )
        candidate_sha = self._commit(repository, "candidate")
        worktree_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        worktree_schema["properties"]["api_routes"]["items"]["properties"][
            "transport_role"
        ]["enum"] = ["metrics"]
        schema_path.write_text(
            json.dumps(worktree_schema, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_git_routes(
            root,
            [_route("WorktreeOnlyLegacy", "query", "/worktree-only")],
        )

        report = self.verifier.build_report(
            root,
            migration_base_sha=base_sha,
            migration_candidate_sha=candidate_sha,
        )

        self.assertEqual(report["policy"]["allowedNonBusinessTransportRoles"], ["health"])
        self.assertEqual(report["summary"]["routes"], 3)
        self.assertEqual(report["summary"]["structuralIssues"], 1)
        self.assertEqual(report["summary"]["migrationObligations"], 2)
        self.assertEqual(
            [issue["operation"] for issue in report["issues"]],
            ["CandidateMutation"],
        )
        self.assertEqual(
            [item["operation"] for item in report["migrationObligations"]],
            ["ExistingLegacy", "CandidateLegacy"],
        )
        self.assertEqual(
            [item["operation"] for item in report["queryRouteClassifications"]],
            ["ExistingLegacy", "CandidateLegacy"],
        )
        self.assertEqual(
            report["migrationRegressions"][0]["identity"]["operation"],
            "CandidateLegacy",
        )
        self.assertEqual(report["migrationBaseline"]["candidateCommitSha"], candidate_sha)
        self.assertEqual(report["migrationBaseline"]["candidateSource"], "git_commit")

    def test_new_legacy_identity_fails_immutable_base_ratchet(self) -> None:
        repository, root = self._git_service_root(
            [_route("ExistingLegacy", "query", "/existing")]
        )
        base_sha = self._commit(repository, "base")
        self._write_git_routes(
            root,
            [
                _route("ExistingLegacy", "query", "/existing"),
                _route("NewLegacy", "query", "/new"),
            ],
        )
        candidate_sha = self._commit(repository, "candidate")

        report = self.verifier.build_report(
            root,
            migration_base_sha=base_sha,
            migration_candidate_sha=candidate_sha,
        )

        self.assertEqual(report["summary"]["migrationRegressions"], 1)
        self.assertEqual(
            report["migrationRegressions"][0]["identity"]["operation"],
            "NewLegacy",
        )

    def test_reidentified_legacy_route_fails_immutable_base_ratchet(self) -> None:
        repository, root = self._git_service_root(
            [_route("LegacyQuery", "query", "/legacy")]
        )
        base_sha = self._commit(repository, "base")
        self._write_git_routes(root, [_route("RenamedLegacy", "query", "/legacy")])
        candidate_sha = self._commit(repository, "candidate")

        report = self.verifier.build_report(
            root,
            migration_base_sha=base_sha,
            migration_candidate_sha=candidate_sha,
        )

        self.assertEqual(report["summary"]["migrationRegressions"], 1)
        self.assertEqual(
            report["migrationRegressions"][0]["code"],
            "GRAPHQL_READ_REST_COMMAND.MIGRATION_OBLIGATION_ADDED_OR_REIDENTIFIED",
        )

    def test_legacy_identity_decrease_passes_immutable_base_ratchet(self) -> None:
        repository, root = self._git_service_root(
            [
                _route("LegacyA", "query", "/legacy-a"),
                _route("LegacyB", "query", "/legacy-b"),
            ]
        )
        base_sha = self._commit(repository, "base")
        self._write_git_routes(root, [_route("LegacyA", "query", "/legacy-a")])
        candidate_sha = self._commit(repository, "candidate")

        report = self.verifier.build_report(
            root,
            migration_base_sha=base_sha,
            migration_candidate_sha=candidate_sha,
        )

        self.assertEqual(report["migrationBaseline"]["baseObligationCount"], 2)
        self.assertEqual(report["migrationBaseline"]["candidateObligationCount"], 1)
        self.assertEqual(report["summary"]["migrationRegressions"], 0)

    def test_non_ancestor_base_and_candidate_fail_closed(self) -> None:
        repository, root = self._git_service_root(
            [_route("LegacyQuery", "query", "/legacy")]
        )
        base_sha = self._commit(repository, "base")
        tree_sha = subprocess.run(
            ["git", "write-tree"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        unrelated_sha = subprocess.run(
            ["git", "commit-tree", tree_sha],
            cwd=repository,
            check=True,
            input="unrelated candidate\n",
            capture_output=True,
            text=True,
        ).stdout.strip()

        with self.assertRaisesRegex(ValueError, "must be an ancestor"):
            self.verifier.build_report(
                root,
                migration_base_sha=base_sha,
                migration_candidate_sha=unrelated_sha,
            )

    def test_make_default_base_falls_back_to_head_without_origin_main(self) -> None:
        repository, root = self._git_service_root(
            [_route("LegacyQuery", "query", "/legacy")]
        )
        head_sha = self._commit(repository, "base")
        make_program = (
            f"include {SERVICE_MAKEFILE_PATH}\n"
            "print-graphql-migration-base:\n"
            "\t@printf '%s\\n' \"$(GRAPHQL_MIGRATION_BASE_SHA)\"\n"
        )

        completed = subprocess.run(
            ["make", "-s", "-f", "-", "print-graphql-migration-base"],
            cwd=root,
            check=False,
            input=make_program,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), head_sha)

    def test_structural_issue_remains_strict_zero_failure(self) -> None:
        root = self._service_root(
            {
                "services/example-service/contracts/example/object/operations.yaml": [
                    _route("Mutation", "command", "/graphql", method="POST")
                ]
            }
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(VERIFIER_PATH),
                "--service-root",
                str(root),
                "--require-structural-zero",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 1, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["summary"]["structuralIssues"], 1)
        self.assertEqual(report["summary"]["migrationObligations"], 0)

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
