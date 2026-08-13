from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001

import argparse
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl


_BASELINE = "sha256:" + ("a" * 64)
_RETIRED_INDEXES = [
    "idx_media_processing_dead_letters_aggregate_time",
    "idx_media_processing_dead_letters_consumer_time",
]


def _args(*, confirmed: bool, expected: int) -> argparse.Namespace:
    return argparse.Namespace(
        confirm_media_processing_dead_letter_index_migration=confirmed,
        expected_retired_index_drop_count=expected,
    )


class MediaProcessingDeadLetterIndexMigrationContractTest(unittest.TestCase):
    def test_parser_exposes_only_confirmed_exact_count_migration(self) -> None:
        parser = stackctl.build_parser()
        parsed = parser.parse_args(
            [
                "repair",
                "--target",
                "alpha-local",
                "--fix",
                "repair-media-processing-dead-letter-indexes",
                "--confirm-media-processing-dead-letter-index-migration",
                "--expected-retired-index-drop-count",
                "2",
            ]
        )
        self.assertTrue(
            parsed.confirm_media_processing_dead_letter_index_migration
        )
        self.assertEqual(parsed.expected_retired_index_drop_count, 2)

    def test_confirmation_and_exact_count_fail_before_runtime_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp) / "unconfirmed"
            with mock.patch.object(
                stackctl,
                "active_consumer_leases",
            ) as leases:
                result = stackctl._repair_media_processing_dead_letter_indexes(
                    _args(confirmed=False, expected=2),
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=report_dir,
                )
            self.assertEqual(result["exitCode"], 2)
            leases.assert_not_called()

            invalid_report_dir = Path(temp) / "invalid-count"
            with mock.patch.object(
                stackctl,
                "active_consumer_leases",
            ) as leases:
                invalid = stackctl._repair_media_processing_dead_letter_indexes(
                    _args(confirmed=True, expected=1),
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=invalid_report_dir,
                )
            self.assertEqual(invalid["exitCode"], 2)
            leases.assert_not_called()

    def test_first_migration_and_replay_are_candidate_bound_and_audited(self) -> None:
        for expected in (2, 0):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                result, report, commands = self._run_migration(
                    root,
                    expected=expected,
                )

                self.assertEqual(result["exitCode"], 0)
                self.assertEqual(report["status"], "passed")
                self.assertFalse(report["apiStarted"])
                self.assertEqual(report["consumerLeases"], [])
                self.assertEqual(report["candidateDigest"], _BASELINE)
                self.assertEqual(
                    report["destructiveRepairPerformed"],
                    expected == 2,
                )
                self.assertEqual(report["destructiveRepairOutcome"], "confirmed")
                self.assertEqual(
                    report["destructiveActions"],
                    [
                        {"action": "drop_index", "index": name}
                        for name in (_RETIRED_INDEXES if expected else [])
                    ],
                )
                migration_commands = [
                    argv
                    for argv in commands
                    if "/usr/local/bin/migrate-media-processing-dead-letter-indexes"
                    in argv
                ]
                self.assertEqual(len(migration_commands), 1)
                command = migration_commands[0]
                self.assertIn("QWQ_STORAGE_MIGRATION_MODE=quiesced_atomic", command)
                self.assertIn("CONTENT_MONGO_DATABASE=quwoquan_content", command)
                self.assertEqual(
                    command[command.index("--expected-drop-count") + 1],
                    str(expected),
                )
                teardown = report["steps"][-1]
                self.assertEqual(teardown["name"], "mongo-teardown")
                self.assertFalse(teardown["volumesPurged"])
                self.assertNotIn("--volumes", teardown["argv"])

    def test_running_runtime_or_candidate_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp) / "running"
            with (
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(stackctl, "active_consumer_leases", return_value=[]),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value={"status": "running"},
                ),
            ):
                result = stackctl._repair_media_processing_dead_letter_indexes(
                    _args(confirmed=True, expected=2),
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=report_dir,
                )
            self.assertEqual(result["exitCode"], 2)
            self.assertIn("stopped runtime", " ".join(result["details"]))

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result, report, _ = self._run_migration(
                root,
                expected=2,
                candidate_drift=True,
            )
            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(report["destructiveRepairOutcome"], "confirmed")
            self.assertTrue(report["destructiveRepairPerformed"])
            self.assertIn("identity changed", " ".join(report["details"]))
            self.assertEqual(report["steps"][-1]["name"], "mongo-teardown")

    def _run_migration(
        self,
        root: Path,
        *,
        expected: int,
        candidate_drift: bool = False,
    ) -> tuple[dict[str, object], dict[str, object], list[list[str]]]:
        report_dir = root / "run"
        report_dir.mkdir(parents=True)
        candidate_root = root / "candidate"
        candidate_root.mkdir()
        (candidate_root / "manifest.json").write_text("{}\n")
        compose = candidate_root / "compose.yaml"
        compose.write_text("services: {}\n")
        candidate_manifest = {
            "releaseInputClassification": "research_inputs",
        }
        snapshot = {"fixed": "snapshot"}
        commands: list[list[str]] = []

        def run(argv: list[str], **_: object) -> CompletedProcess[str]:
            commands.append(argv)
            if "/usr/local/bin/migrate-media-processing-dead-letter-indexes" in argv:
                dropped = _RETIRED_INDEXES if expected else []
                migration_report = (
                    report_dir
                    / "media-processing-dead-letter-index-migration.json"
                )
                migration_report.write_text(
                    json.dumps(
                        {
                            "schema": (
                                "quwoquan.content."
                                "media_processing_dead_letter_index_migration.v1"
                            ),
                            "status": "passed",
                            "database": "quwoquan_content",
                            "migrationMode": "quiesced_atomic",
                            "expectedDropCount": expected,
                            "droppedIndexes": dropped,
                            "retiredIndexesAbsent": True,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
            return CompletedProcess(argv, 0, "", "")

        assert_snapshot = (
            mock.Mock(side_effect=ValueError("candidate identity changed"))
            if candidate_drift
            else mock.Mock()
        )
        with (
            mock.patch.object(
                stackctl,
                "_local_stack_operation_lock",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch.object(stackctl, "active_consumer_leases", return_value=[]),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={"status": "stopped", "attemptId": "attempt-a"},
            ),
            mock.patch.object(
                stackctl,
                "active_deployment_candidate_snapshot",
                return_value=snapshot,
            ),
            mock.patch.object(
                stackctl,
                "_fixed_candidate_identity",
                return_value=(_BASELINE, candidate_root, candidate_manifest),
            ),
            mock.patch.object(
                stackctl.active_content_release_outbox_repair,
                "topology_compose_files",
                return_value=[compose],
            ),
            mock.patch.object(
                stackctl.active_content_release_outbox_repair,
                "materialize_candidate_runtime_inputs",
                return_value={"environment": {}, "evidence": {"exact": True}},
            ),
            mock.patch.object(
                stackctl,
                "verify_certificate",
                return_value={"certificate": "/tls/cert", "privateKey": "/tls/key"},
            ),
            mock.patch.object(
                stackctl,
                "_candidate_bindings_from_snapshot",
                return_value=(
                    {"providerRuntime": {}, "candidateRoot": candidate_root},
                    {"composition": {}, "candidateRoot": candidate_root},
                ),
            ),
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "_gamma_env_from_port_manifest",
                return_value={},
            ),
            mock.patch.object(
                stackctl,
                "_provider_runtime_launch_environment",
                return_value={},
            ),
            mock.patch.object(
                stackctl,
                "_observability_log_sink_launch_environment",
                return_value={},
            ),
            mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
            mock.patch.object(
                stackctl,
                "_bind_gamma_packaged_service_image_refs",
                return_value={},
            ),
            mock.patch.object(stackctl, "_bind_gamma_packaged_configuration_digest"),
            mock.patch.object(
                stackctl,
                "_formal_release_compose_project_name",
                return_value="quwoquan_alpha_release",
            ),
            mock.patch.object(
                stackctl,
                "compose_file_args",
                return_value=["-f", str(compose)],
            ),
            mock.patch.object(
                stackctl,
                "assert_active_deployment_candidate_snapshot",
                assert_snapshot,
            ),
            mock.patch.object(stackctl, "run", side_effect=run),
        ):
            result = stackctl._repair_media_processing_dead_letter_indexes(
                _args(confirmed=True, expected=expected),
                environment="alpha",
                target_name="alpha-local",
                report_dir=report_dir,
            )
        report = json.loads((report_dir / "report.json").read_text())
        return result, report, commands


if __name__ == "__main__":
    unittest.main()
