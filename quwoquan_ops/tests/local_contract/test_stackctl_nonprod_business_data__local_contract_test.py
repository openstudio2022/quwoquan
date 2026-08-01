"""stackctl owns the non-production business-data verification entrypoint.

spec_ref: specs/feature-tree/spec.md#uat-009
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


class StackctlNonprodBusinessDataContractTest(unittest.TestCase):
    def test_reconcile_cli_is_confirmed_receipt_only_and_prod_forbidden(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "repair",
                "--target",
                "alpha-local",
                "--fix",
                "reconcile-nonprod-data",
            ]
        )
        self.assertFalse(args.confirm_nonprod_data_reconcile)
        with tempfile.TemporaryDirectory() as directory:
            result = stackctl._reconcile_nonprod_data(
                args,
                environment="alpha",
                target_name="alpha-local",
                report_dir=Path(directory),
            )
        self.assertEqual(result["exitCode"], 2)
        self.assertIn("--confirm-nonprod-data-reconcile", "\n".join(result["details"]))

        with tempfile.TemporaryDirectory() as directory:
            result = stackctl._reconcile_nonprod_data(
                argparse.Namespace(confirm_nonprod_data_reconcile=True),
                environment="prod",
                target_name="prod-sim",
                report_dir=Path(directory),
            )
        self.assertEqual(result["exitCode"], 2)
        self.assertIn("forbidden", result["summary"])

    def test_confirmed_reconcile_is_a_noop_without_eligible_receipts(self) -> None:
        topology = {
            "targets": {
                "alpha-local": {
                    "env": "alpha",
                    "publicBases": {
                        "api": "https://api.alpha.quwoquan.local:17000"
                    },
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.object(stackctl, "active_deployment_candidate", return_value=None),
                mock.patch.object(stackctl, "env_runs_root", return_value=root),
                mock.patch.object(stackctl, "load_environment_topology", return_value=topology),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value=topology["targets"]["alpha-local"],
                ),
                mock.patch.object(
                    stackctl.NonprodDataProvisioner,
                    "cleanup_candidate_bound_data",
                ) as cleanup,
            ):
                result = stackctl._reconcile_nonprod_data(
                    argparse.Namespace(confirm_nonprod_data_reconcile=True),
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=root / "report",
                )
        self.assertEqual(result["exitCode"], 0)
        self.assertIn("no stale", "\n".join(result["details"]))
        cleanup.assert_not_called()

    def test_failed_prerequisites_emit_gate_block_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            with mock.patch.object(
                stackctl,
                "run_nonprod_business_data_verification",
            ) as run_verification:
                result = stackctl._run_nonprod_business_data_profile(
                    argparse.Namespace(),
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=report_dir,
                    prerequisites_passed=False,
                )

        self.assertEqual(result["status"], "GATE_BLOCK")
        self.assertEqual(result["executed"], 0)
        self.assertEqual(result["skipped"], 0)
        run_verification.assert_not_called()

    def test_bound_evidence_is_delegated_to_the_canonical_runner(self) -> None:
        manifest = {
            "baselineId": "sha256:" + "1" * 64,
            "packageDigest": "sha256:" + "2" * 64,
        }
        readiness = {"passed": True}
        expected = {
            "status": "passed",
            "executed": 6,
            "skipped": 0,
        }
        topology = {
            "targets": {
                "alpha-local": {
                    "env": "alpha",
                    "publicBases": {
                        "api": "https://api.alpha.quwoquan.local:17000"
                    },
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence.json"
            evidence.write_text(json.dumps({}), encoding="utf-8")
            report_dir = root / "report"
            with (
                mock.patch.object(stackctl, "output_root", return_value=root),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": manifest["baselineId"]},
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value=manifest,
                ),
                mock.patch.object(
                    stackctl,
                    "_load_data_release_readiness",
                    return_value=(readiness, root / "readiness.json"),
                ),
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value=topology,
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value=topology["targets"]["alpha-local"],
                ),
                mock.patch.object(
                    stackctl,
                    "run_nonprod_business_data_verification",
                    return_value=expected,
                ) as run_verification,
            ):
                result = stackctl._run_nonprod_business_data_profile(
                    argparse.Namespace(
                        data_release_id="release",
                        data_verify_run_id="verify",
                        data_manifest_digest="sha256:" + "3" * 64,
                        nonprod_data_evidence=str(evidence),
                    ),
                    environment="alpha",
                    target_name="alpha-local",
                    report_dir=report_dir,
                    prerequisites_passed=True,
                )

        self.assertEqual(result, expected)
        run_verification.assert_called_once()
        self.assertEqual(
            run_verification.call_args.kwargs["base_url"],
            "https://api.alpha.quwoquan.local:17000",
        )

    def test_data_inspect_summarizes_receipts_without_copying_objects(self) -> None:
        topology = {
            "targets": {
                "alpha-local": {"env": "alpha", "portProfile": "alpha-local"}
            }
        }
        receipt = {
            "schema": "qwq.nonprod_acceptance_dataset_receipt",
            "datasetId": "nonprod_reference_identity",
            "datasetEpoch": "e" * 64,
            "baselineId": "sha256:" + "1" * 64,
            "packageDigest": "sha256:" + "2" * 64,
            "releaseDigest": "sha256:" + "3" * 64,
            "retentionClass": "candidate_bound",
            "status": "passed",
            "cleanupState": "retained",
            "expiresAt": "2030-01-01T00:00:00+00:00",
            "createdObjectIdsOrHashes": {"ownerIds": ["private-owner"]},
            "projectionWatermarks": {"cursor": "private-cursor"},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt_path = root / "nonprod-data" / ("e" * 64) / "receipt.json"
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with (
                mock.patch.object(
                    stackctl, "load_environment_topology", return_value=topology
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value=topology["targets"]["alpha-local"],
                ),
                mock.patch.object(stackctl, "load_port_manifest", return_value={}),
                mock.patch.object(stackctl, "canonical_port", return_value=17000),
                mock.patch.object(stackctl, "env_runs_root", return_value=root),
                mock.patch.object(
                    stackctl,
                    "_candidate_workspace_report",
                    return_value={
                        "status": "current",
                        "drifted": False,
                        "issues": [],
                    },
                ),
            ):
                report = stackctl._data_report("alpha-local")

        self.assertFalse(report["realDataOnly"])
        self.assertEqual(len(report["nonprodAcceptanceDatasets"]), 1)
        serialized = json.dumps(report)
        self.assertNotIn("private-owner", serialized)
        self.assertNotIn("private-cursor", serialized)

    def test_candidate_workspace_report_exposes_managed_input_drift(self) -> None:
        candidate = {
            "baselineId": "sha256:" + "1" * 64,
            "sourceRevision": "a" * 40,
            "workspaceStatusDigest": "sha256:" + "2" * 64,
            "workspaceDigest": "sha256:" + "3" * 64,
        }
        current = {
            "baselineId": "sha256:" + "4" * 64,
            "sourceRevision": "b" * 40,
            "workspaceStatusDigest": "sha256:" + "5" * 64,
            "deploymentInputDigest": "sha256:" + "6" * 64,
            "deploymentInputFileCount": 42,
        }
        topology = {"targets": {"alpha-local": {"env": "alpha"}}}
        with (
            mock.patch.object(
                stackctl, "load_environment_topology", return_value=topology
            ),
            mock.patch.object(
                stackctl,
                "get_target",
                return_value=topology["targets"]["alpha-local"],
            ),
            mock.patch.object(
                stackctl,
                "active_deployment_candidate",
                return_value={"baselineId": candidate["baselineId"]},
            ),
            mock.patch.object(
                stackctl, "load_candidate_manifest", return_value=candidate
            ),
            mock.patch.object(stackctl, "workspace_snapshot", return_value=current),
        ):
            report = stackctl._candidate_workspace_report("alpha-local")

        self.assertEqual(report["status"], "drifted")
        self.assertTrue(report["drifted"])
        self.assertEqual(
            report["mismatchedFields"],
            [
                "baselineId",
                "sourceRevision",
                "workspaceStatusDigest",
                "deploymentInputDigest",
            ],
        )
        self.assertEqual(report["current"]["deploymentInputFileCount"], 42)


if __name__ == "__main__":
    unittest.main()
