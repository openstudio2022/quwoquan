# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
# spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-004
from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
import argparse
import hashlib
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.tests.support.rollout_stage_promotion_evidence_test_support import (
    promotion_evidence,
)


def candidate_material_promotion_evidence(
    *, candidate_id: str, candidate_material_id: str, stage: str
) -> dict[str, object]:
    value = promotion_evidence(
        candidate_id=candidate_id,
        artifact_digest=candidate_material_id,
        stage=stage,
    )
    value["candidateMaterialId"] = value.pop("artifactDigest")
    unsigned = dict(value)
    unsigned.pop("evidenceDigest")
    value["evidenceDigest"] = "sha256:" + hashlib.sha256(
        hosted_release_ledger._canonical_bytes(unsigned)
    ).hexdigest()
    return value


class ProdReleaseTransactionContractTest(unittest.TestCase):
    def test_prod_registry_attestations_are_verified_concurrently(self) -> None:
        rendezvous = threading.Barrier(2, timeout=2)
        manifest = {
            "source": {"repository": "owner/repo"},
            "environmentArtifacts": {
                "prod": {
                    "images": {
                        "content-service": {
                            "ref": "ghcr.io/owner/repo/content-service-prod@sha256:"
                            + ("a" * 64)
                        },
                        "user-service": {
                            "ref": "ghcr.io/owner/repo/user-service-prod@sha256:"
                            + ("b" * 64)
                        },
                    }
                }
            },
        }

        def verify(*_args: object, **_kwargs: object) -> None:
            rendezvous.wait()

        with (
            patch.object(
                stackctl.oci_supply_chain,
                "verify_oci_supply_chain",
                side_effect=verify,
            ) as verify_mock,
            patch.object(stackctl, "_remaining_deadline_seconds", return_value=30),
        ):
            stackctl._verify_release_registry_attestations(
                manifest,
                deadline_epoch=100,
            )

        self.assertEqual(verify_mock.call_count, 2)

    def test_formal_rollout_has_no_release_evidence_manifest_loader(self) -> None:
        self.assertFalse(hasattr(stackctl, "_deployable_release_manifest"))
        parser = stackctl.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "deploy",
                    "--target",
                    "prod-hosted",
                    "--release-manifest",
                    "/tmp/legacy.json",
                ]
            )

    def test_release_ledger_is_cas_ordered_and_receipted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary).resolve()
            from_digest = "sha256:" + ("a" * 64)
            to_digest = "sha256:" + ("b" * 64)
            request = {
                "schema": hosted_release_ledger.REQUEST_SCHEMA,
                "prodActivationAdmissionRef": "ghcr.io/owner/prod-admission@sha256:" + ("6" * 64),
                "prodActivationAdmissionOciDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionPayloadDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionId": "sha256:" + ("6" * 64),
                "candidateMaterialManifestRef": "ghcr.io/owner/release-tag@sha256:" + ("7" * 64),
                "candidateMaterialManifestOciDigest": "sha256:" + ("7" * 64),
                "candidateMaterialManifestPayloadDigest": "sha256:" + ("7" * 64),
                                "previousReleasedRef": "ghcr.io/owner/released@sha256:" + ("e" * 64),
                                "previousReleasedOciDigest": "sha256:" + ("e" * 64),
                "previousReleasedPayloadDigest": "sha256:" + ("e" * 64),
                "previousReleasedId": "sha256:" + ("f" * 64),
                "service": "prod-stack",
                "fromCandidateDigest": from_digest,
                "toCandidateDigest": to_digest,
                "step": "0",
                "stage": "canary",
                "triggerStage": "canary",
                "fromServiceFactoryOciDigest": (
                    from_digest
                ),
                "toServiceFactoryOciDigest": (
                    to_digest
                ),
                "fromAppFactoryOciDigest": "sha256:" + "1" * 64,
                "toAppFactoryOciDigest": "sha256:" + "1" * 64,
                "decision": "continue",
                "rollbackOutcome": "not_triggered",
                "rollbackEvidence": {"triggered": False},
                "candidateMaterialId": to_digest,
                "imageDigest": to_digest,
                "configDigest": to_digest,
                "contractGraphDigest": to_digest,
                "adapterDigest": to_digest,
                "expectedGeneration": 0,
                "sloReadback": {
                    "source": "prometheus",
                    "promotionEvidence": candidate_material_promotion_evidence(
                        candidate_id=to_digest,
                        candidate_material_id=to_digest,
                        stage="canary",
                    ),
                },
                "postChecks": [
                    {
                        "name": "health",
                        "status": "passed",
                        "receiptDigest": to_digest,
                    }
                ],
                "lastGoodCandidateDigest": from_digest,
                "verifiedAt": "2026-07-26T00:00:00+00:00",
            }
            readback = hosted_release_ledger.commit(state_dir, request)
            self.assertEqual(readback["state"]["generation"], "1")
            self.assertRegex(readback["receiptRef"], r"^receipt:hosted:[0-9a-f]{64}$")
            self.assertEqual(
                hosted_release_ledger.fetch(state_dir, "prod-stack"),
                readback,
            )
            action, generation = stackctl._validate_release_transition(
                readback["state"],
                from_candidate_digest=from_digest,
                to_candidate_digest=to_digest,
                stage="5",
            )
            self.assertEqual((action, generation), ("advance", 1))
            with self.assertRaisesRegex(RuntimeError, "CAS conflict"):
                hosted_release_ledger.commit(state_dir, request)

            receipt_path = state_dir / "receipts" / (
                readback["receipt"]["receiptId"] + ".json"
            )
            receipt_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "digest or ledger binding"):
                hosted_release_ledger.fetch(state_dir, "prod-stack")

    def test_release_ledger_serializes_advance_and_rollback_contention(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary).resolve()
            source = "sha256:" + ("a" * 64)
            candidate = "sha256:" + ("b" * 64)
            check = {
                "name": "health",
                "status": "passed",
                "receiptDigest": candidate,
            }
            initial = {
                "schema": hosted_release_ledger.REQUEST_SCHEMA,
                "prodActivationAdmissionRef": "ghcr.io/owner/prod-admission@sha256:" + ("6" * 64),
                "prodActivationAdmissionOciDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionPayloadDigest": "sha256:" + ("6" * 64),
                "prodActivationAdmissionId": "sha256:" + ("6" * 64),
                "candidateMaterialManifestRef": "ghcr.io/owner/release-tag@sha256:" + ("7" * 64),
                "candidateMaterialManifestOciDigest": "sha256:" + ("7" * 64),
                "candidateMaterialManifestPayloadDigest": "sha256:" + ("7" * 64),
                                "previousReleasedRef": "ghcr.io/owner/released@sha256:" + ("e" * 64),
                                "previousReleasedOciDigest": "sha256:" + ("e" * 64),
                "previousReleasedPayloadDigest": "sha256:" + ("e" * 64),
                "previousReleasedId": "sha256:" + ("f" * 64),
                "service": "prod-stack",
                "fromCandidateDigest": source,
                "toCandidateDigest": candidate,
                "step": "0",
                "stage": "canary",
                "triggerStage": "canary",
                "fromServiceFactoryOciDigest": source,
                "toServiceFactoryOciDigest": candidate,
                "fromAppFactoryOciDigest": "sha256:" + "1" * 64,
                "toAppFactoryOciDigest": "sha256:" + "1" * 64,
                "decision": "continue",
                "rollbackOutcome": "not_triggered",
                "rollbackEvidence": {"triggered": False},
                "candidateMaterialId": candidate,
                "imageDigest": candidate,
                "configDigest": candidate,
                "contractGraphDigest": candidate,
                "adapterDigest": candidate,
                "expectedGeneration": 0,
                "sloReadback": {
                    "source": "prometheus",
                    "promotionEvidence": candidate_material_promotion_evidence(
                        candidate_id=candidate,
                        candidate_material_id=candidate,
                        stage="canary",
                    ),
                },
                "postChecks": [check],
                "lastGoodCandidateDigest": source,
                "verifiedAt": "2026-07-26T00:00:00+00:00",
            }
            hosted_release_ledger.commit(state_dir, initial)

            advance = dict(initial)
            advance.update(
                {
                    "step": "5",
                    "stage": "5",
                    "triggerStage": "5",
                    "expectedGeneration": 1,
                    "verifiedAt": "2026-07-26T00:00:01+00:00",
                    "sloReadback": {
                        "source": "prometheus",
                        "promotionEvidence": candidate_material_promotion_evidence(
                        candidate_id=candidate,
                        candidate_material_id=candidate,
                        stage="5",
                    ),
                    },
                }
            )
            rollback = dict(initial)
            rollback.update(
                {
                    "fromCandidateDigest": candidate,
                    "toCandidateDigest": source,
                    "step": "100",
                    "stage": "100",
                    "triggerStage": "canary",
                    "fromServiceFactoryOciDigest": candidate,
                    "toServiceFactoryOciDigest": source,
                    "fromAppFactoryOciDigest": "sha256:" + "1" * 64,
                    "toAppFactoryOciDigest": "sha256:" + "1" * 64,
                    "decision": "rolled_back",
                    "rollbackOutcome": "rolled_back",
                    "rollbackEvidence": {
                        "triggered": True,
                        "startedAt": "2026-07-26T00:00:00+00:00",
                        "endedAt": "2026-07-26T00:00:01+00:00",
                        "durationMs": 1000,
                        "postChecks": [check],
                    },
                    "expectedGeneration": 1,
                    "lastGoodCandidateDigest": source,
                    "verifiedAt": "2026-07-26T00:00:01+00:00",
                }
            )

            barrier = threading.Barrier(2)
            successes: list[dict[str, object]] = []
            failures: list[Exception] = []

            def contend(request: dict[str, object]) -> None:
                barrier.wait()
                try:
                    successes.append(hosted_release_ledger.commit(state_dir, request))
                except Exception as error:  # asserted as the losing CAS below
                    failures.append(error)

            threads = [
                threading.Thread(target=contend, args=(advance,)),
                threading.Thread(target=contend, args=(rollback,)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(failures), 1)
            self.assertRegex(str(failures[0]), "CAS conflict")
            readback = hosted_release_ledger.fetch(state_dir, "prod-stack")
            self.assertEqual(readback["state"]["generation"], "2")
            self.assertIn(
                readback["state"]["decision"],
                {"continue", "rolled_back"},
            )
            self.assertEqual(len(list((state_dir / "receipts").glob("*.json"))), 2)

    def test_warning_slo_pauses_gray_but_rolls_back_full(self) -> None:
        self.assertEqual(
            stackctl._decision_from_slo_output(
                "decision=pause reason=warning_threshold",
                "canary",
            ),
            ("pause", "slo gate decision=pause"),
        )

    def test_insufficient_samples_pause_even_at_full_without_false_rollback(self) -> None:
        decision, reason = stackctl._decision_from_slo_output(
            "decision=pause reason=insufficient_samples",
            "100",
        )
        self.assertEqual(decision, "pause")
        self.assertIn("insufficient", reason)

    def test_operator_receipt_readback_accepts_only_hosted_candidate_binding(self) -> None:
        from_digest = "sha256:" + ("a" * 64)
        digest = "sha256:" + ("b" * 64)
        receipt = {
            "schema": hosted_release_ledger.RECEIPT_SCHEMA,
            "prodActivationAdmissionRef": "ghcr.io/owner/prod-admission@sha256:" + ("6" * 64),
            "prodActivationAdmissionOciDigest": "sha256:" + ("6" * 64),
            "prodActivationAdmissionPayloadDigest": "sha256:" + ("6" * 64),
            "prodActivationAdmissionId": "sha256:" + ("6" * 64),
            "candidateMaterialManifestRef": "ghcr.io/owner/release-tag@sha256:" + ("7" * 64),
            "candidateMaterialManifestOciDigest": "sha256:" + ("7" * 64),
            "candidateMaterialManifestPayloadDigest": "sha256:" + ("7" * 64),
            "previousReleasedRef": "ghcr.io/owner/released@sha256:" + ("e" * 64),
            "previousReleasedOciDigest": "sha256:" + ("e" * 64),
            "previousReleasedPayloadDigest": "sha256:" + ("e" * 64),
            "previousReleasedId": "sha256:" + ("f" * 64),
            "authority": hosted_release_ledger.AUTHORITY,
            "service": "prod-stack",
            "fromCandidateDigest": from_digest,
            "toCandidateDigest": digest,
            "step": "100",
            "stage": "100",
            "triggerStage": "100",
            "fromServiceFactoryOciDigest": (
                from_digest
            ),
            "toServiceFactoryOciDigest": (
                digest
            ),
            "fromAppFactoryOciDigest": "sha256:" + "1" * 64,
            "toAppFactoryOciDigest": "sha256:" + "1" * 64,
            "decision": "continue",
            "rollbackOutcome": "not_triggered",
            "rollbackEvidence": {"triggered": False},
            "candidateMaterialId": digest,
            "imageDigest": digest,
            "configDigest": digest,
            "contractGraphDigest": digest,
            "adapterDigest": digest,
            "expectedGeneration": 2,
            "committedGeneration": 3,
            "sloReadback": {
                "promotionEvidence": candidate_material_promotion_evidence(
                        candidate_id=digest,
                        candidate_material_id=digest,
                        stage="100",
                    )
            },
            "postChecks": [],
            "lastGoodCandidateDigest": digest,
            "verifiedAt": "2026-07-26T00:00:00+00:00",
        }
        receipt_id = hosted_release_ledger._receipt_id(receipt)
        receipt["receiptId"] = receipt_id
        readback = {
            "schema": hosted_release_ledger.RECEIPT_READBACK_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        }
        args = argparse.Namespace(
            service="prod-stack",
            receipt_id=receipt_id,
            purpose="last-good",
            image_digest=digest,
            config_digest=digest,
            contract_graph_digest=digest,
            adapter_digest=digest,
            candidate_digest=digest,
        )
        with patch.object(
            stackctl,
            "_run_hosted_release_ledger",
            return_value=readback,
        ):
            result = stackctl.command_hosted_release_receipt(args)
        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["receiptRef"], f"receipt:hosted:{receipt_id}")

        rollback_receipt = dict(receipt)
        rollback_receipt.update(
            {
                "fromCandidateDigest": digest,
                "toCandidateDigest": from_digest,
                "decision": "rolled_back",
                "rollbackOutcome": "rolled_back",
                "rollbackEvidence": {
                    "triggered": True,
                    "startedAt": "2026-07-25T23:59:58Z",
                    "endedAt": "2026-07-25T23:59:59Z",
                    "durationMs": 1000,
                    "postChecks": [
                        {
                            "name": "rollback-health",
                            "status": "passed",
                            "receiptDigest": digest,
                        }
                    ],
                },
                "lastGoodCandidateDigest": from_digest,
            }
        )
        rollback_id = hosted_release_ledger._receipt_id(rollback_receipt)
        rollback_receipt["receiptId"] = rollback_id
        rollback_readback = {
            "schema": hosted_release_ledger.RECEIPT_READBACK_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "receipt": rollback_receipt,
            "receiptRef": f"receipt:hosted:{rollback_id}",
        }
        args.receipt_id = rollback_id
        args.purpose = "rollback"
        args.candidate_digest = from_digest
        with patch.object(
            stackctl,
            "_run_hosted_release_ledger",
            return_value=rollback_readback,
        ):
            result = stackctl.command_hosted_release_receipt(args)
        self.assertEqual(result["exitCode"], 0)

        args.receipt_id = receipt_id
        args.purpose = "last-good"
        args.candidate_digest = digest
        args.adapter_digest = "sha256:" + ("c" * 64)
        with patch.object(
            stackctl,
            "_run_hosted_release_ledger",
            return_value=readback,
        ):
            result = stackctl.command_hosted_release_receipt(args)
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            stackctl._decision_from_slo_output(
                "decision=pause reason=warning_threshold",
                "100",
            ),
            ("rollback", "100 rollout cannot remain paused on warning SLO"),
        )
