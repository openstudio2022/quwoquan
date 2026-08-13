"""Alpha-only service-core cutover safety contracts.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/service-core-composition/spec.md#gwt-001.t2
"""

from __future__ import annotations

import tempfile
import unittest
from subprocess import CompletedProcess
from pathlib import Path

from quwoquan_ops.cli.lib import service_core_cutover
from quwoquan_ops.cli.lib.service_core_composition import SERVICE_CORE_MODULES

_IMAGE_ID = (  # sha256("image")
    "sha256:6105d6cc76af400325e94d588ce511be5bfdbb73b437dc51eca43917d7a43e3d"
)
_CONFIG_HASH = (  # sha256("config")
    "sha256:b79606fb3afea5bd1609ed40b622142f1c98125abcfe89a76a661b0e8e343910"
)


def _projection() -> dict[str, object]:
    services: dict[str, object] = {
        "service-core": {
            "networks": {
                "default": {"aliases": list(SERVICE_CORE_MODULES)}
            }
        }
    }
    for service in (
        service_core_cutover.MANDATORY_STANDALONE
        | service_core_cutover.MANDATORY_INFRA
    ):
        services[service] = (
            {"image": f"canonical/{service}:test"}
            if service in service_core_cutover.MANDATORY_INFRA
            else {}
        )
    return {"services": services}


class ServiceCoreCutoverContractTest(unittest.TestCase):
    def test_failed_candidate_evidence_is_persisted_before_stop_or_remove(
        self,
    ) -> None:
        calls: list[list[str]] = []
        inspected = {
            "Id": "candidate-id",
            "Name": "/service-core-candidate",
            "Image": _IMAGE_ID,
            "Config": {
                "Image": "service-core:test",
                "Env": ["POSTGRES_DSN=secret", "APP_ENV=alpha"],
                "Labels": {
                    "com.docker.compose.config-hash": _CONFIG_HASH
                },
            },
            "State": {
                "Status": "exited",
                "ExitCode": 1,
                "OOMKilled": False,
                "Health": {"Status": "unhealthy", "Log": []},
            },
            "Mounts": [],
            "NetworkSettings": {"Networks": {"shadow": {}}},
        }

        def runner(
            command: list[str],
            **_kwargs: object,
        ) -> CompletedProcess[str]:
            calls.append(command)
            if command[1:3] == ["logs", "--timestamps"]:
                return CompletedProcess(command, 0, "first failure\n", "")
            if command[1] == "inspect":
                import json

                return CompletedProcess(command, 0, json.dumps([inspected]), "")
            return CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as temporary:
            evidence = (
                service_core_cutover._capture_candidate_failure_evidence(
                    runner,
                    inspected,
                    Path(temporary),
                )
            )
            runner(["docker", "stop", "candidate-id"])
            self.assertEqual(calls[0][1], "logs")
            self.assertEqual(calls[1][1], "inspect")
            self.assertEqual(calls[2][1], "stop")
            payload = Path(evidence["evidencePath"]).read_text()
            self.assertIn('"APP_ENV"', payload)
            self.assertIn('"POSTGRES_DSN"', payload)
            self.assertNotIn("secret", payload)
            self.assertEqual(
                Path(evidence["logsPath"]).read_text(),
                "first failure\n",
            )

    def test_empty_database_without_ledger_allows_canonical_bootstrap(
        self,
    ) -> None:
        calls: list[list[str]] = []

        def runner(
            command: list[str],
            **_kwargs: object,
        ) -> CompletedProcess[str]:
            calls.append(command)
            return CompletedProcess(command, 0, "0\t0\n", "")

        validated = service_core_cutover._verify_user_migration_integrity(
            runner,
            {"Id": "postgres-empty"},
        )

        self.assertTrue(validated["emptyDatabaseBootstrap"])
        self.assertEqual(validated["appliedCount"], 0)
        self.assertGreater(validated["sourceCount"], 0)
        self.assertEqual(len(calls), 1)

    def test_non_empty_database_without_ledger_is_blocked(
        self,
    ) -> None:
        def runner(
            command: list[str],
            **_kwargs: object,
        ) -> CompletedProcess[str]:
            return CompletedProcess(command, 0, "0\t1\n", "")

        with self.assertRaisesRegex(
            ValueError,
            "missing from a non-empty database",
        ):
            service_core_cutover._verify_user_migration_integrity(
                runner,
                {"Id": "postgres-non-empty"},
            )

    def test_migration_integrity_requires_every_applied_file_unchanged(
        self,
    ) -> None:
        validated = service_core_cutover._validate_user_migration_integrity(
            ledger_checksums={"account/object/001_create.up.sql": "sha256-a"},
            source_checksums={"account/object/001_create.up.sql": "sha256-a"},
        )
        self.assertEqual(validated["status"], "passed")

        with self.assertRaisesRegex(ValueError, "missing from source"):
            service_core_cutover._validate_user_migration_integrity(
                ledger_checksums={"account/object/001_create.up.sql": "sha256-a"},
                source_checksums={},
            )

        with self.assertRaisesRegex(ValueError, "checksum drift"):
            service_core_cutover._validate_user_migration_integrity(
                ledger_checksums={"account/object/001_create.up.sql": "sha256-a"},
                source_checksums={
                    "account/object/001_create.up.sql": "sha256-changed"
                },
            )

    def test_mongo_recommendation_topology_requires_shared_alias_and_volume(
        self,
    ) -> None:
        mongo = {
            "NetworkSettings": {
                "Networks": {
                    "quwoquan_alpha_test_live_default": {
                        "Aliases": ["mongodb"]
                    }
                }
            },
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": "alpha-mongo",
                    "Destination": "/data/db",
                    "RW": True,
                }
            ],
        }
        recommendation = {
            "NetworkSettings": {
                "Networks": {
                    "quwoquan_alpha_test_live_default": {
                        "Aliases": ["recommendation-service"]
                    }
                }
            },
            "Config": {
                "Env": [
                    "MONGODB_URI=mongodb://mongodb:27017/?directConnection=true",
                    "MONGODB_DATABASE=quwoquan_recommendation",
                ]
            },
        }
        validated = (
            service_core_cutover._validate_mongo_recommendation_topology(
                {
                    "mongodb": [mongo],
                    "recommendation-service": [recommendation],
                }
            )
        )
        self.assertEqual(validated["mongoVolume"], "alpha-mongo")

        mongo["NetworkSettings"]["Networks"][
            "quwoquan_alpha_test_live_default"
        ]["Aliases"] = ["wrong"]
        with self.assertRaisesRegex(ValueError, "DNS alias"):
            service_core_cutover._validate_mongo_recommendation_topology(
                {
                    "mongodb": [mongo],
                    "recommendation-service": [recommendation],
                }
            )

    def test_mongo_recommendation_topology_rejects_uri_or_volume_drift(
        self,
    ) -> None:
        mongo = {
            "NetworkSettings": {
                "Networks": {"default": {"Aliases": ["mongodb"]}}
            },
            "Mounts": [
                {
                    "Type": "bind",
                    "Destination": "/data/db",
                    "RW": True,
                }
            ],
        }
        recommendation = {
            "NetworkSettings": {
                "Networks": {"default": {"Aliases": ["recommendation-service"]}}
            },
            "Config": {
                "Env": [
                    "MONGODB_URI=mongodb://other:27017",
                    "MONGODB_DATABASE=quwoquan_recommendation",
                ]
            },
        }
        with self.assertRaisesRegex(ValueError, "URI drifted"):
            service_core_cutover._validate_mongo_recommendation_topology(
                {
                    "mongodb": [mongo],
                    "recommendation-service": [recommendation],
                }
            )
        recommendation["Config"]["Env"][0] = (
            "MONGODB_URI=mongodb://mongodb:27017/?directConnection=true"
        )
        with self.assertRaisesRegex(ValueError, "writable named volume"):
            service_core_cutover._validate_mongo_recommendation_topology(
                {
                    "mongodb": [mongo],
                    "recommendation-service": [recommendation],
                }
            )

    def test_projection_requires_one_core_and_all_module_aliases(self) -> None:
        validated = service_core_cutover._validate_projection(_projection())
        self.assertEqual(
            set(validated["coreAliases"]),
            set(SERVICE_CORE_MODULES),
        )

        missing_alias = _projection()
        missing_alias["services"]["service-core"]["networks"]["default"][
            "aliases"
        ] = list(SERVICE_CORE_MODULES[:-1])
        with self.assertRaisesRegex(ValueError, "aliases"):
            service_core_cutover._validate_projection(missing_alias)

    def test_projection_rejects_split_core_coexistence(self) -> None:
        coexistence = _projection()
        coexistence["services"]["search-service"] = {}
        with self.assertRaisesRegex(ValueError, "split core"):
            service_core_cutover._validate_projection(coexistence)

    def test_infrastructure_runtime_image_must_match_projection(self) -> None:
        projection = service_core_cutover._validate_projection(_projection())
        by_service = {
            service: [
                {
                    "Config": {
                        "Image": f"canonical/{service}:test",
                    }
                }
            ]
            for service in service_core_cutover.MANDATORY_INFRA
        }
        service_core_cutover._validate_infra_projection_identity(
            by_service,
            projection,
        )
        by_service["elasticsearch"][0]["Config"]["Image"] = (
            "docker.elastic.co/elasticsearch/elasticsearch:8.13.4"
        )
        with self.assertRaisesRegex(ValueError, "image identity is stale"):
            service_core_cutover._validate_infra_projection_identity(
                by_service,
                projection,
            )

    def test_execute_rejects_non_alpha_or_implicit_volume_policy(self) -> None:
        rendered = {
            "plan": {
                "composeProject": service_core_cutover.PROJECT,
            },
            "environment": {},
            "composeFiles": [],
            "composeProfiles": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            common = {
                "compose_project": service_core_cutover.PROJECT,
                "report_dir": Path(temporary),
                "rendered": rendered,
                "workspace_before": {},
                "workspace_after_build": lambda: {},
                "leases": [],
                "runner": lambda *_args, **_kwargs: None,
                "commit_runtime": lambda _plan: {},
            }
            with self.assertRaisesRegex(ValueError, "alpha-local"):
                service_core_cutover.execute(
                    target="beta-local",
                    preserve_volumes=True,
                    **common,
                )
            with self.assertRaisesRegex(ValueError, "preserve-volumes"):
                service_core_cutover.execute(
                    target="alpha-local",
                    preserve_volumes=False,
                    **common,
                )

    def test_execute_rejects_active_consumer_lease_before_docker(self) -> None:
        rendered = {
            "plan": {
                "composeProject": service_core_cutover.PROJECT,
            },
            "environment": {},
            "composeFiles": [],
            "composeProfiles": [],
        }
        called = False

        def runner(*_args: object, **_kwargs: object) -> None:
            nonlocal called
            called = True

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "consumer lease"):
                service_core_cutover.execute(
                    target="alpha-local",
                    compose_project=service_core_cutover.PROJECT,
                    preserve_volumes=True,
                    report_dir=Path(temporary),
                    rendered=rendered,
                    workspace_before={},
                    workspace_after_build=lambda: {},
                    leases=[{"leaseId": "lease"}],
                    runner=runner,
                    commit_runtime=lambda _plan: {},
                )
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
