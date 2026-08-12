from __future__ import annotations

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-002.t1
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-002.t2
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-002.t5
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-002.t6

import argparse
import contextlib
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import active_content_release_outbox_repair as repair


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_post_bindings(count: int) -> list[dict[str, object]]:
    bindings: list[dict[str, object]] = []
    for index in range(count):
        post_ref = f"article/体验/legacy-{index}/1"
        post_id = "data_post_" + hashlib.sha256(
            f"qwq-content-post:posts/{post_ref}".encode()
        ).hexdigest()
        bindings.append(
            {
                "postRef": post_ref,
                "postId": post_id,
                "contentId": f"qwq_data_{post_id}",
                "contentVersion": 1,
                "usageScope": "research",
                "contentType": "article",
                "authorId": "builtin_travel_blogger",
            }
        )
    return bindings


class ActiveContentReleaseOutboxRepairContractTest(unittest.TestCase):
    def test_candidate_runtime_inputs_are_materialized_from_exact_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidate = root / "candidate"
            shared = candidate / "packages/runtime-shared"
            shared.mkdir(parents=True)
            shared_files = {
                "Caddyfile": b"caddy\n",
                "livekit.yaml": b"port: 7880\n",
                "module_catalog.yaml": b"modules: []\n",
                "object-storage-lifecycle.json": b"{}\n",
                "retention_policy.yaml": b"policies: []\n",
            }
            provenance: dict[str, object] = {}
            for name, content in shared_files.items():
                path = shared / name
                path.write_bytes(content)
                provenance[name] = {
                    "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                    "source": f"source/{name}",
                }
            _write_json(
                shared / "manifest.json",
                {
                    "schema": "qwq.runtime_shared_package",
                    "environment": "alpha",
                    "provenance": {"files": provenance},
                },
            )
            service = candidate / "packages/services/content-service"
            config = service / "config/config.yaml"
            config.parent.mkdir(parents=True)
            config.write_text("service: content\n")
            config_digest = "sha256:" + hashlib.sha256(config.read_bytes()).hexdigest()
            config_version = "sha256:" + ("a" * 64)
            _write_json(
                service / "provenance.json",
                {
                    "service": "content-service",
                    "environment": "alpha",
                    "configVersion": config_version,
                    "digests": {"config": config_digest},
                },
            )
            recommendation = candidate / "packages/services/recommendation-service"
            recommendation_config = recommendation / "config/config.yaml"
            recommendation_config.parent.mkdir(parents=True)
            recommendation_config.write_text("service: recommendation\n")
            recommendation_digest = "sha256:" + hashlib.sha256(
                recommendation_config.read_bytes()
            ).hexdigest()
            recommendation_version = "sha256:" + ("b" * 64)
            _write_json(
                recommendation / "provenance.json",
                {
                    "service": "recommendation-service",
                    "environment": "alpha",
                    "configVersion": recommendation_version,
                    "digests": {"config": recommendation_digest},
                },
            )
            policy = (
                shared
                / "runtime-topology/policies/recommendation_policy.yaml"
            )
            policy.parent.mkdir(parents=True)
            policy.write_text("version: 1\n")
            legal = candidate / "packages/legal-static/current/public"
            legal.mkdir(parents=True)

            result = repair.materialize_candidate_runtime_inputs(
                candidate,
                root / "run",
                environment="alpha",
            )

            environment = result["environment"]
            self.assertEqual(
                environment["LOCAL_GAMMA_CADDYFILE"],
                str((shared / "Caddyfile").resolve()),
            )
            self.assertEqual(
                environment["LOCAL_GAMMA_OBJECT_STORAGE_LIFECYCLE_FILE"],
                str((shared / "object-storage-lifecycle.json").resolve()),
            )
            self.assertEqual(
                environment["QWQ_COMPOSE_CONTENT_SERVICE_CONFIG_VERSION"],
                config_version,
            )
            self.assertEqual(
                environment["QWQ_COMPOSE_RECOMMENDATION_SERVICE_CONFIG_VERSION"],
                recommendation_version,
            )
            materialized_config = (
                Path(environment["QWQ_COMPOSE_CONFIG_ROOT"])
                / "content-service.yaml"
            )
            self.assertEqual(materialized_config.read_bytes(), config.read_bytes())
            self.assertEqual(
                (
                    Path(environment["QWQ_COMPOSE_CONFIG_ROOT"])
                    / "recommendation-service.yaml"
                ).read_bytes(),
                recommendation_config.read_bytes(),
            )
            self.assertEqual(result["evidence"]["configDigest"], config_digest)
            self.assertEqual(
                result["evidence"]["serviceConfigDigests"],
                {
                    "content-service": config_digest,
                    "recommendation-service": recommendation_digest,
                },
            )

            config.write_text("tampered: true\n")
            with self.assertRaisesRegex(
                repair.ActiveContentReleaseOutboxRepairError,
                "config digest mismatch",
            ):
                repair.materialize_candidate_runtime_inputs(
                    candidate,
                    root / "tampered-run",
                    environment="alpha",
                )

    def test_release_receipts_topology_and_repair_audits_are_exact(self) -> None:
        digest = "sha256:" + ("a" * 64)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            release_root = root / "data/releases/release-a"
            (release_root / "payload").mkdir(parents=True)
            (release_root / "payload/desired_state.json").write_text("{}\n")
            attestation = release_root / "attestations/release.json"
            attestation_digest = _write_json(
                attestation,
                {
                    "releaseId": "release-a",
                    "payloadSha256": digest,
                    "sourceOwner": "qwq_data",
                },
            )
            import_path = root / "runs/data-release/release-a/run/import.json"
            _write_json(
                import_path,
                {
                    "schema": "quwoquan.content_import_report",
                    "status": "active",
                    "environment": "alpha",
                    "releaseId": "release-a",
                    "sourceOwner": "qwq_data",
                    "manifestDigest": digest,
                    "mode": "sync",
                    "deletePolicy": "tombstone",
                    "counts": {
                        "postsLoaded": 46,
                        "postsUpserted": 46,
                        "postsRemoved": 4,
                        "outboxEventsAppended": 50,
                    },
                    "postBindings": _legacy_post_bindings(46),
                },
            )
            _write_json(
                import_path.parent / "creator-import.json",
                {
                    "schema": "quwoquan.user_creator_import_report",
                    "status": "active",
                    "environment": "alpha",
                    "releaseId": "release-a",
                    "sourceOwner": "qwq_data",
                },
            )
            candidate_root = root / "candidate"
            topology_root = candidate_root / "packages/runtime-shared/runtime-topology"
            compose_entries = []
            for role, layer, service, relative in (
                ("ops-base", "base", "", "base.compose.yaml"),
                (
                    "service",
                    "base",
                    "content-service",
                    "services/content-service/base.compose.yaml",
                ),
                (
                    "service",
                    "environment",
                    "content-service",
                    "services/content-service/environment.compose.yaml",
                ),
                (
                    "service",
                    "base",
                    "recommendation-service",
                    "services/recommendation-service/base.compose.yaml",
                ),
                (
                    "control-plane",
                    "base",
                    "",
                    "control-plane/platform-ops.compose.yaml",
                ),
            ):
                path = topology_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("services:\n  content-service: {}\n")
                compose_entries.append(
                    {
                        "role": role,
                        "layer": layer,
                        "service": service,
                        "ref": str(path.relative_to(candidate_root)),
                        "digest": "sha256:"
                        + hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
            _write_json(topology_root / "manifest.json", {"compose": compose_entries})
            observability_compose = (
                candidate_root
                / "packages/runtime-shared/observability-log-sink/elasticsearch.compose.yaml"
            )
            observability_compose.parent.mkdir(parents=True, exist_ok=True)
            observability_compose.write_text("services:\n  elasticsearch: {}\n")
            observability_digest = "sha256:" + hashlib.sha256(
                observability_compose.read_bytes()
            ).hexdigest()
            snapshot = {
                "manifest": {
                    "observabilityLogSink": {
                        "composeRef": str(
                            observability_compose.relative_to(candidate_root)
                        ),
                        "composeDigest": observability_digest,
                    },
                    "release": {
                        "candidate": {
                            "releaseId": "release-a",
                            "releaseDigest": digest,
                            "attestationRef": str(attestation),
                            "attestationDigest": attestation_digest,
                        }
                    }
                }
            }

            source = repair.validate_source_import_report(
                import_path,
                environment="alpha",
            )
            self.assertEqual(source["postBindingCount"], 46)
            binding = repair.validate_candidate_release_binding(snapshot, source)
            creator = repair.validate_creator_receipt(
                import_path,
                environment="alpha",
                release_id="release-a",
            )
            compose = repair.topology_compose_files(
                candidate_root,
                snapshot["manifest"],
            )

            self.assertEqual(binding["releaseRoot"], str(release_root.resolve()))
            self.assertEqual(
                creator["path"],
                str((import_path.parent / "creator-import.json").resolve()),
            )
            self.assertEqual(
                compose,
                [
                    (topology_root / "base.compose.yaml").resolve(),
                    (
                        topology_root
                        / "services/content-service/base.compose.yaml"
                    ).resolve(),
                    (
                        topology_root
                        / "services/recommendation-service/base.compose.yaml"
                    ).resolve(),
                    (
                        topology_root
                        / "services/content-service/environment.compose.yaml"
                    ).resolve(),
                    (
                        topology_root / "control-plane/platform-ops.compose.yaml"
                    ).resolve(),
                    observability_compose.resolve(),
                ],
            )

            repair_report = root / "repair.json"
            source_bindings_digest = source["postBindingsDigest"]
            _write_json(
                repair_report,
                {
                    "schema": "quwoquan.content_import_report",
                    "status": "active",
                    "environment": "alpha",
                    "releaseId": "release-a",
                    "manifestDigest": digest,
                    "sourceOwner": "qwq_data",
                    "mode": "sync",
                    "deletePolicy": "tombstone",
                    "counts": {
                        "postsLoaded": 46,
                        "postsUpserted": 46,
                        "postsRemoved": 0,
                        "outboxEventsReady": 1,
                        "outboxEventsAppended": 0,
                    },
                    "postBindings": _legacy_post_bindings(46),
                    "auditEvents": [
                        "DataReleasePrepared",
                        "DataReleaseReplayValidated",
                        "DataReleaseOutboxRepair|count=1",
                        "DataReleaseOutboxEventRepair|eventId=event-a|"
                        f"beforeSha256={'sha256:' + 'b' * 64}|"
                        f"afterSha256={'sha256:' + 'c' * 64}",
                    ],
                },
            )
            evidence = repair.validate_repair_report(
                repair_report,
                environment="alpha",
                release_id="release-a",
                manifest_digest=digest,
                expected_repair_count=1,
                expected_post_binding_count=46,
                expected_post_bindings_digest=source_bindings_digest,
            )
            self.assertEqual(evidence["repairCount"], 1)
            with self.assertRaisesRegex(ValueError, "closure drift"):
                repair.validate_repair_report(
                    repair_report,
                    environment="alpha",
                    release_id="release-a",
                    manifest_digest=digest,
                    expected_repair_count=0,
                    expected_post_binding_count=46,
                    expected_post_bindings_digest=source_bindings_digest,
                )

    def test_command_requires_confirmation_before_lock_or_runtime(self) -> None:
        args = argparse.Namespace(
            confirm_active_content_release_outbox_repair=False,
            expected_outbox_repair_count=4,
            content_import_report="/not/read.json",
        )
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            stackctl,
            "_local_stack_operation_lock",
        ) as operation_lock, mock.patch.object(stackctl, "_write_summary_bundle"):
            result = stackctl._repair_active_content_release_outbox(
                args,
                environment="alpha",
                target_name="alpha-local",
                report_dir=Path(temp),
            )
        self.assertEqual(result["exitCode"], 2)
        operation_lock.assert_not_called()

    def test_command_rejects_active_lease_or_running_runtime_before_candidate_use(self) -> None:
        args = argparse.Namespace(
            confirm_active_content_release_outbox_repair=True,
            expected_outbox_repair_count=4,
            content_import_report="/must/not/be/read.json",
        )
        for name, leases, startup, expected_detail in (
            (
                "active lease",
                [{"leaseId": "lease-a"}],
                None,
                "active Content outbox repair requires zero consumer leases",
            ),
            (
                "running runtime",
                [],
                {"status": "running"},
                "active Content outbox repair requires an absent or stopped runtime receipt",
            ),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                candidate = mock.Mock()
                runtime = mock.Mock(return_value=startup)
                with (
                    mock.patch.object(
                        stackctl,
                        "_local_stack_operation_lock",
                        return_value=contextlib.nullcontext(),
                    ),
                    mock.patch.object(
                        stackctl,
                        "active_consumer_leases",
                        return_value=leases,
                    ),
                    mock.patch.object(stackctl, "load_startup_attempt", runtime),
                    mock.patch.object(
                        stackctl,
                        "active_deployment_candidate_snapshot",
                        candidate,
                    ),
                    mock.patch.object(stackctl, "_write_summary_bundle"),
                    mock.patch.object(stackctl, "relpath", side_effect=str),
                ):
                    result = stackctl._repair_active_content_release_outbox(
                        args,
                        environment="alpha",
                        target_name="alpha-local",
                        report_dir=Path(temp),
                    )
            self.assertEqual(result["exitCode"], 2)
            self.assertIn(expected_detail, result["details"])
            candidate.assert_not_called()
            if leases:
                runtime.assert_not_called()

    def test_command_rejects_count_outside_zero_or_source_deletion_closure(self) -> None:
        baseline = "sha256:" + ("a" * 64)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            import_path = (
                root / "env/alpha/runs/data-release/release-a/run/import.json"
            )
            import_path.parent.mkdir(parents=True)
            import_path.write_text("{}\n")
            args = argparse.Namespace(
                confirm_active_content_release_outbox_repair=True,
                expected_outbox_repair_count=2,
                content_import_report=str(import_path),
            )
            release_binding = mock.Mock()
            with (
                mock.patch.object(stackctl, "output_root", return_value=root),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl, "active_consumer_leases", return_value=[]
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value={"status": "stopped"},
                ),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate_snapshot",
                    return_value={"manifest": {}},
                ),
                mock.patch.object(
                    stackctl,
                    "_fixed_candidate_identity",
                    return_value=(baseline, root / "candidate", {}),
                ),
                mock.patch.object(
                    repair,
                    "validate_source_import_report",
                    return_value={
                        "releaseId": "release-a",
                        "manifestDigest": baseline,
                        "legacyDeletionCount": 4,
                    },
                ),
                mock.patch.object(
                    repair, "validate_candidate_release_binding", release_binding
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl._repair_active_content_release_outbox(
                    args,
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=root / "report",
                )
        self.assertEqual(result["exitCode"], 2)
        self.assertTrue(
            any(
                "source import legacy deletion count" in detail
                for detail in result["details"]
            )
        )
        release_binding.assert_not_called()

    def test_command_runs_only_mongo_packaged_importer_and_no_volume_purge(self) -> None:
        baseline = "sha256:" + ("d" * 64)
        release_digest = "sha256:" + ("e" * 64)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report_dir = root / "report"
            candidate_root = root / "candidate"
            candidate_root.mkdir()
            (candidate_root / "manifest.json").write_text("{}\n")
            import_path = root / "output/env/alpha/runs/data-release/r/run/import.json"
            import_path.parent.mkdir(parents=True)
            import_path.write_text("{}\n")
            release_root = root / "output/data/releases/r"
            release_root.mkdir(parents=True)
            creator = import_path.parent / "creator-import.json"
            creator.write_text("{}\n")
            compose_files = [root / f"compose-{index}.yaml" for index in range(3)]
            for path in compose_files:
                path.write_text("services: {}\n")
            snapshot = {
                "manifest": {"releaseInputClassification": "research_inputs"}
            }
            args = argparse.Namespace(
                confirm_active_content_release_outbox_repair=True,
                expected_outbox_repair_count=4,
                content_import_report=str(import_path),
            )
            commands: list[list[str]] = []
            command_environments: list[dict[str, str]] = []

            fail_cleanup = False
            fail_import = False

            def run(argv: list[str], **_kwargs: object) -> CompletedProcess[str]:
                commands.append(argv)
                command_environments.append(dict(_kwargs.get("env") or {}))
                if fail_import and "/usr/local/bin/content-import" in argv:
                    return CompletedProcess(argv, 1, "", "import failed")
                if fail_cleanup and argv[-2:] == ["down", "--remove-orphans"]:
                    return CompletedProcess(argv, 1, "", "cleanup failed")
                return CompletedProcess(argv, 0, "ok", "")

            environment = {
                "LOCAL_GAMMA_MEDIA_IMAGE_BASE_URL": "https://media/image",
                "LOCAL_GAMMA_MEDIA_VIDEO_BASE_URL": "https://media/video",
                "LOCAL_GAMMA_MEDIA_AVATAR_BASE_URL": "https://media/avatar",
            }
            repair_evidence = {
                "path": str(report_dir / "content-import-repair.json"),
                "digest": "sha256:" + ("f" * 64),
                "repairCount": 4,
                "repairs": [{"eventId": f"event-{i}"} for i in range(4)],
            }
            stackctl_patches = {
                "output_root": mock.Mock(return_value=root / "output"),
                "_local_stack_operation_lock": mock.Mock(
                    return_value=contextlib.nullcontext()
                ),
                "active_consumer_leases": mock.Mock(return_value=[]),
                "load_startup_attempt": mock.Mock(
                    return_value={"status": "stopped"}
                ),
                "active_deployment_candidate_snapshot": mock.Mock(
                    return_value=snapshot
                ),
                "_fixed_candidate_identity": mock.Mock(
                    return_value=(baseline, candidate_root, snapshot["manifest"])
                ),
                "_candidate_bindings_from_snapshot": mock.Mock(
                    return_value=(
                        {"providerRuntime": {}, "candidateRoot": candidate_root},
                        {"composition": {}, "candidateRoot": candidate_root},
                    )
                ),
                "_gamma_env_from_port_manifest": mock.Mock(
                    return_value=environment.copy()
                ),
                "_provider_runtime_launch_environment": mock.Mock(return_value={}),
                "_observability_log_sink_launch_environment": mock.Mock(
                    return_value={}
                ),
                "_bind_gamma_down_parse_environment": mock.Mock(),
                "_bind_gamma_packaged_service_image_refs": mock.Mock(
                    return_value={}
                ),
                "_bind_gamma_packaged_configuration_digest": mock.Mock(),
                "verify_certificate": mock.Mock(
                    return_value={
                        "certificate": root / "tls/certificate.pem",
                        "privateKey": root / "tls/private-key.pem",
                    }
                ),
                "_formal_release_compose_project_name": mock.Mock(
                    return_value="qwq-alpha"
                ),
                "run": mock.Mock(side_effect=run),
                "assert_active_deployment_candidate_snapshot": mock.Mock(),
                "_write_summary_bundle": mock.Mock(),
                "relpath": mock.Mock(side_effect=str),
            }
            repair_patches = {
                "validate_source_import_report": mock.Mock(
                    return_value={
                        "releaseId": "r",
                        "manifestDigest": release_digest,
                        "legacyDeletionCount": 4,
                        "postBindingCount": 46,
                        "postBindingsDigest": baseline,
                    }
                ),
                "validate_candidate_release_binding": mock.Mock(
                    return_value={
                        "releaseId": "r",
                        "manifestDigest": release_digest,
                        "releaseRoot": str(release_root),
                    }
                ),
                "validate_creator_receipt": mock.Mock(
                    return_value={"path": str(creator), "digest": baseline}
                ),
                "topology_compose_files": mock.Mock(return_value=compose_files),
                "materialize_candidate_runtime_inputs": mock.Mock(
                    return_value={
                        "environment": {
                            "LOCAL_GAMMA_CADDYFILE": "/candidate/Caddyfile",
                            "QWQ_COMPOSE_CONFIG_ROOT": "/run/config-root",
                        },
                        "evidence": {"configDigest": baseline},
                    }
                ),
                "validate_repair_report": mock.Mock(return_value=repair_evidence),
            }
            with mock.patch.multiple(
                stackctl, **stackctl_patches
            ), mock.patch.multiple(repair, **repair_patches):
                result = stackctl._repair_active_content_release_outbox(
                    args,
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=report_dir,
                )

                commands.clear()
                command_environments.clear()
                stackctl_patches[
                    "assert_active_deployment_candidate_snapshot"
                ].side_effect = ValueError("candidate drifted")
                drifted = stackctl._repair_active_content_release_outbox(
                    args,
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=report_dir,
                )
                drift_commands = list(commands)
                drift_report = json.loads(
                    (report_dir / "report.json").read_text()
                )

                commands.clear()
                command_environments.clear()
                stackctl_patches[
                    "assert_active_deployment_candidate_snapshot"
                ].side_effect = None
                fail_cleanup = True
                cleanup_failed = stackctl._repair_active_content_release_outbox(
                    args,
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=report_dir,
                )
                cleanup_report = json.loads(
                    (report_dir / "report.json").read_text()
                )

                commands.clear()
                command_environments.clear()
                fail_cleanup = False
                fail_import = True
                import_failed = stackctl._repair_active_content_release_outbox(
                    args,
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=report_dir,
                )
                import_failed_report = json.loads(
                    (report_dir / "report.json").read_text()
                )

            self.assertEqual(result["exitCode"], 0, result)
            self.assertEqual(
                [command[-1] for command in commands[:3]],
                ["--services", "mongodb", "mongo-init"],
            )
            self.assertEqual(
                command_environments[0]["LOCAL_GAMMA_CADDYFILE"],
                "/candidate/Caddyfile",
            )
            self.assertEqual(
                command_environments[0]["QWQ_PUBLIC_TLS_CERT_FILE"],
                str(root / "tls/certificate.pem"),
            )
            self.assertEqual(
                cleanup_report["runtimeInputs"],
                {"configDigest": baseline},
            )
            import_command = commands[3]
            self.assertIn("/usr/local/bin/content-import", import_command)
            self.assertIn("--require-replay", import_command)
            self.assertIn("--replay-source-import-report", import_command)
            self.assertIn(
                f"{import_path.resolve()}:/repair/source-import.json:ro",
                import_command,
            )
            replay_report_index = import_command.index(
                "--replay-source-import-report"
            )
            self.assertEqual(
                import_command[replay_report_index + 1],
                "/repair/source-import.json",
            )
            self.assertNotIn("api-edge", import_command)
            teardown = commands[-1]
            self.assertEqual(teardown[-2:], ["down", "--remove-orphans"])
            self.assertNotIn("--volumes", teardown)
            self.assertNotIn("-v", teardown)
            self.assertEqual(drifted["exitCode"], 2)
            self.assertIn("candidate drifted", drifted["details"])
            self.assertTrue(drift_report["destructiveRepairAttempted"])
            self.assertEqual(
                drift_report["destructiveRepairOutcome"], "confirmed"
            )
            self.assertTrue(drift_report["destructiveRepairPerformed"])
            self.assertEqual(
                drift_report["destructiveActions"], repair_evidence["repairs"]
            )
            self.assertEqual(
                drift_commands[-1][-2:], ["down", "--remove-orphans"]
            )
            self.assertEqual(cleanup_failed["exitCode"], 2)
            self.assertEqual(
                cleanup_report["resourceReleaseIssues"], ["cleanup failed"]
            )
            self.assertEqual(import_failed["exitCode"], 2)
            self.assertIn("import failed", import_failed["details"])
            self.assertTrue(
                import_failed_report["destructiveRepairAttempted"]
            )
            self.assertEqual(
                import_failed_report["destructiveRepairOutcome"], "unknown"
            )
            self.assertIsNone(
                import_failed_report["destructiveRepairPerformed"]
            )
            self.assertEqual(import_failed_report["destructiveActions"], [])


if __name__ == "__main__":
    unittest.main()
