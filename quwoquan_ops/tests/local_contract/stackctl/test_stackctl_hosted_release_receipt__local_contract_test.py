# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-002
from __future__ import annotations

import copy
import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod import hosted_release_ledger


class HostedReleaseReceiptContractTest(unittest.TestCase):
    _DIGEST = "sha256:" + "a" * 64
    _FROM_CANDIDATE = "sha256:" + "b" * 64
    _TO_CANDIDATE = "sha256:" + "c" * 64
    _NEXT_CANDIDATE = "sha256:" + "d" * 64
    _SERVICE = "mainline"

    def _candidate(self) -> dict[str, str]:
        return {
            "imageDigest": self._DIGEST,
            "configDigest": self._DIGEST,
            "contractGraphDigest": self._DIGEST,
            "adapterDigest": self._DIGEST,
        }

    def _admission(self) -> dict[str, str]:
        return {
            "prodActivationAdmissionRef": self._DIGEST,
            "prodActivationAdmissionOciDigest": self._DIGEST,
            "prodActivationAdmissionPayloadDigest": self._DIGEST,
            "prodActivationAdmissionId": self._DIGEST,
            "candidateMaterialManifestRef": self._FROM_CANDIDATE,
            "candidateMaterialManifestOciDigest": self._FROM_CANDIDATE,
            "candidateMaterialManifestPayloadDigest": self._FROM_CANDIDATE,
            "previousReleasedRef": self._NEXT_CANDIDATE,
            "previousReleasedOciDigest": self._NEXT_CANDIDATE,
            "previousReleasedPayloadDigest": self._NEXT_CANDIDATE,
            "previousReleasedId": self._FROM_CANDIDATE,
        }

    def _commit(
        self,
        *,
        state_dir: Path,
        stage: str,
        decision: str,
        generation: int,
        from_candidate: str = _FROM_CANDIDATE,
        to_candidate: str = _TO_CANDIDATE,
        trigger_stage: str | None = None,
        last_good: str | None = None,
        artifact_digest: str = _DIGEST,
    ) -> tuple[dict[str, str], dict[str, object]]:
        resolved_last_good = last_good or (
            to_candidate
            if stage == "100" and decision in {"continue", "rolled_back"}
            else from_candidate
        )
        result = hosted_release_ledger.commit(
            state_dir,
            {
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
                "service": self._SERVICE,
                "fromCandidateDigest": from_candidate,
                "toCandidateDigest": to_candidate,
                "step": {"canary": "0", "50": "50", "100": "100"}[stage],
                "stage": stage,
                "triggerStage": trigger_stage or stage,
                "fromServiceFactoryOciDigest": (
                    from_candidate
                ),
                "toServiceFactoryOciDigest": (
                    to_candidate
                ),
                "fromAppFactoryOciDigest": f"sha256:" + ("1" * 64),
                "toAppFactoryOciDigest": f"sha256:" + ("1" * 64),
                "decision": decision,
                "rollbackOutcome": (
                    decision
                    if decision in {"rolled_back", "rollback_failed"}
                    else "not_triggered"
                ),
                "rollbackEvidence": (
                    {
                        "triggered": True,
                        "startedAt": "2026-07-25T23:59:58Z",
                        "endedAt": "2026-07-25T23:59:59Z",
                        "durationMs": 1000,
                        "postChecks": [
                            {
                                "name": "rollback-health",
                                "status": (
                                    "passed"
                                    if decision == "rolled_back"
                                    else "failed"
                                ),
                                "receiptDigest": self._DIGEST,
                            }
                        ],
                    }
                    if decision in {"rolled_back", "rollback_failed"}
                    else {"triggered": False}
                ),
                "candidateMaterialId": artifact_digest,
                **self._candidate(),
                "expectedGeneration": generation,
                "sloReadback": {"values": {"errorRate": 0.001}},
                "postChecks": [
                    {
                        "name": "hosted-health",
                        "status": "passed",
                        "receiptDigest": self._DIGEST,
                    }
                ],
                "lastGoodCandidateDigest": resolved_last_good,
                "verifiedAt": "2026-07-26T00:00:00Z",
            },
        )
        return dict(result["state"]), dict(result["receipt"])

    def test_gray_carry_on_and_full_receipts_bind_immutable_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            first, gray_receipt = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            second, carry_receipt = self._commit(
                state_dir=state_dir,
                stage="50",
                decision="continue",
                generation=1,
            )
            third, full_receipt = self._commit(
                state_dir=state_dir,
                stage="100",
                decision="continue",
                generation=2,
            )
            readback = hosted_release_ledger.fetch(state_dir, self._SERVICE)

        self.assertEqual(
            [first["stage"], second["stage"], third["stage"]],
            ["canary", "50", "100"],
        )
        for receipt, expected_generation, expected_last_good in (
            (gray_receipt, 1, self._FROM_CANDIDATE),
            (carry_receipt, 2, self._FROM_CANDIDATE),
            (full_receipt, 3, self._TO_CANDIDATE),
        ):
            self.assertEqual(
                {
                    "imageDigest": receipt["imageDigest"],
                    "configDigest": receipt["configDigest"],
                    "contractGraphDigest": receipt["contractGraphDigest"],
                    "adapterDigest": receipt["adapterDigest"],
                },
                self._candidate(),
            )
            self.assertEqual(receipt["committedGeneration"], expected_generation)
            self.assertEqual(
                receipt["lastGoodCandidateDigest"],
                expected_last_good,
            )
            self.assertEqual(
                receipt["postChecks"],
                [
                    {
                        "name": "hosted-health",
                        "status": "passed",
                        "receiptDigest": self._DIGEST,
                    }
                ],
            )
            self.assertEqual(receipt["decision"], "continue")
            self.assertEqual(receipt["rollbackEvidence"], {"triggered": False})
        self.assertEqual(readback["authority"], "prod-hosted-service-plane")
        self.assertEqual(readback["receipt"], full_receipt)
        self.assertEqual(
            readback["receiptRef"],
            f"receipt:hosted:{full_receipt['receiptId']}",
        )
        self.assertEqual(first["canary_receipt_id"], gray_receipt["receiptId"])
        self.assertEqual(first["percent_50_receipt_id"], "")
        self.assertEqual(first["percent_100_receipt_id"], "")
        self.assertEqual(second["canary_receipt_id"], gray_receipt["receiptId"])
        self.assertEqual(second["percent_50_receipt_id"], carry_receipt["receiptId"])
        self.assertEqual(second["percent_100_receipt_id"], "")
        self.assertEqual(third["canary_receipt_id"], gray_receipt["receiptId"])
        self.assertEqual(third["percent_50_receipt_id"], carry_receipt["receiptId"])
        self.assertEqual(third["percent_100_receipt_id"], full_receipt["receiptId"])

    def test_successful_and_failed_rollback_are_distinct_receipt_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            _, success = self._commit(
                state_dir=state_dir,
                stage="100",
                decision="rolled_back",
                generation=0,
                from_candidate=self._TO_CANDIDATE,
                to_candidate=self._FROM_CANDIDATE,
            )
            _, failure = self._commit(
                state_dir=state_dir,
                stage="100",
                decision="rollback_failed",
                generation=1,
            )

        self.assertEqual(success["decision"], "rolled_back")
        self.assertEqual(success["rollbackOutcome"], "rolled_back")
        self.assertEqual(success["rollbackEvidence"]["durationMs"], 1000)
        self.assertEqual(
            success["rollbackEvidence"]["postChecks"][0]["status"], "passed"
        )
        self.assertEqual(failure["decision"], "rollback_failed")
        self.assertEqual(failure["rollbackOutcome"], "rollback_failed")
        self.assertEqual(
            failure["rollbackEvidence"]["postChecks"][0]["status"], "failed"
        )

    def test_rollback_evidence_rejects_non_exact_or_invented_facts(self) -> None:
        with self.assertRaisesRegex(ValueError, "only triggered=false"):
            hosted_release_ledger.validate_rollback_evidence(
                {"triggered": False, "durationMs": 0},
                decision="continue",
                rollback_outcome="not_triggered",
                verified_at="2026-07-26T00:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "non-empty passed"):
            hosted_release_ledger.validate_rollback_evidence(
                {
                    "triggered": True,
                    "startedAt": "2026-07-25T23:59:58Z",
                    "endedAt": "2026-07-25T23:59:59Z",
                    "durationMs": 1000,
                    "postChecks": [],
                },
                decision="rolled_back",
                rollback_outcome="rolled_back",
                verified_at="2026-07-26T00:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "not canonically bound"):
            hosted_release_ledger.validate_rollback_evidence(
                {"triggered": False},
                decision="rollback_failed",
                rollback_outcome="not_triggered",
                verified_at="2026-07-26T00:00:00Z",
            )

    def test_check_summary_never_treats_missing_exit_code_as_passed(self) -> None:
        checks = stackctl._release_check_receipts(
            [
                {"exitCode": 0, "summary": "healthy"},
                {"exitCode": None, "summary": "missing"},
                {"summary": "absent"},
            ]
        )
        self.assertEqual(
            [item["status"] for item in checks],
            ["passed", "failed", "failed"],
        )

    def test_new_target_resets_stage_receipt_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            self._commit(
                state_dir=state_dir,
                stage="50",
                decision="continue",
                generation=1,
            )
            _, old_full = self._commit(
                state_dir=state_dir,
                stage="100",
                decision="continue",
                generation=2,
            )
            new_state, new_gray = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=3,
                from_candidate=self._TO_CANDIDATE,
                to_candidate=self._NEXT_CANDIDATE,
            )

        self.assertNotEqual(new_gray["receiptId"], old_full["receiptId"])
        self.assertEqual(
            {
                field: new_state[field]
                for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values()
            },
            {
                "canary_receipt_id": new_gray["receiptId"],
                "percent_5_receipt_id": "",
                "percent_20_receipt_id": "",
                "percent_50_receipt_id": "",
                "percent_100_receipt_id": "",
            },
        )

    def test_same_candidate_rejects_evidence_drift_before_state_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            first_state, _ = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            with self.assertRaisesRegex(RuntimeError, "evidence drifted"):
                self._commit(
                    state_dir=state_dir,
                    stage="50",
                    decision="continue",
                    generation=1,
                    artifact_digest=self._NEXT_CANDIDATE,
                )
            readback = hosted_release_ledger.fetch(state_dir, self._SERVICE)

        self.assertEqual(readback["state"], first_state)

    def test_rollback_preserves_history_and_updates_its_trigger_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            _, gray = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            _, carry = self._commit(
                state_dir=state_dir,
                stage="50",
                decision="continue",
                generation=1,
            )
            rollback_state, rollback = self._commit(
                state_dir=state_dir,
                stage="100",
                trigger_stage="50",
                decision="rolled_back",
                generation=2,
                from_candidate=self._TO_CANDIDATE,
                to_candidate=self._FROM_CANDIDATE,
                last_good=self._FROM_CANDIDATE,
            )
            readback = hosted_release_ledger.fetch(state_dir, self._SERVICE)

        self.assertNotEqual(carry["receiptId"], rollback["receiptId"])
        self.assertEqual(
            rollback_state["canary_receipt_id"],
            gray["receiptId"],
        )
        self.assertEqual(
            rollback_state["percent_50_receipt_id"],
            rollback["receiptId"],
        )
        self.assertEqual(rollback_state["percent_100_receipt_id"], "")
        self.assertEqual(readback["state"], rollback_state)

    @staticmethod
    def _write_state(path: Path, state: dict[str, str]) -> None:
        path.write_text(
            "\n".join(f"{key}={value}" for key, value in state.items()) + "\n",
            encoding="utf-8",
        )

    def test_transition_rejects_retired_release_evidence_shape_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            _, receipt = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            request = {
                key: receipt[key]
                for key in hosted_release_ledger.REQUEST_FIELDS
                if key != "schema"
            }
            request["schema"] = hosted_release_ledger.REQUEST_SCHEMA
            request["fromReleaseEvidenceRef"] = "ghcr.io/owner/release@" + self._FROM_CANDIDATE
            state_before = (state_dir / f"{self._SERVICE}.state").read_bytes()
            with self.assertRaisesRegex(ValueError, "invalid shape"):
                hosted_release_ledger.commit(state_dir, request)
            self.assertEqual(
                (state_dir / f"{self._SERVICE}.state").read_bytes(),
                state_before,
            )

    def test_fetch_rejects_old_state_without_fixed_history_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            state, _ = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            state.pop("percent_100_receipt_id")
            self._write_state(state_dir / f"{self._SERVICE}.state", state)
            with self.assertRaisesRegex(RuntimeError, "shape is not canonical"):
                hosted_release_ledger.fetch(state_dir, self._SERVICE)
            with self.assertRaisesRegex(RuntimeError, "shape is not canonical"):
                self._commit(
                    state_dir=state_dir,
                    stage="50",
                    decision="continue",
                    generation=1,
                )

    def test_fetch_rejects_missing_or_unbound_history_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            state, _ = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            state["percent_50_receipt_id"] = "f" * 64
            self._write_state(state_dir / f"{self._SERVICE}.state", state)
            with self.assertRaisesRegex(RuntimeError, "receipt is missing"):
                hosted_release_ledger.fetch(state_dir, self._SERVICE)

        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            state, current = self._commit(
                state_dir=state_dir,
                stage="canary",
                decision="continue",
                generation=0,
            )
            unrelated = dict(current)
            unrelated.update(
                {
                    "fromCandidateDigest": self._NEXT_CANDIDATE,
                    "toCandidateDigest": self._DIGEST,
                    "triggerStage": "50",
                    "fromServiceFactoryOciDigest": self._NEXT_CANDIDATE,
                    "toServiceFactoryOciDigest": (
                        self._DIGEST
                    ),
                }
            )
            unrelated.pop("receiptId")
            unrelated_id = hosted_release_ledger._receipt_id(unrelated)
            unrelated["receiptId"] = unrelated_id
            receipt_path = state_dir / "receipts" / f"{unrelated_id}.json"
            receipt_path.write_text(
                json.dumps(unrelated, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            state["percent_50_receipt_id"] = unrelated_id
            self._write_state(state_dir / f"{self._SERVICE}.state", state)
            with self.assertRaisesRegex(RuntimeError, "candidate-transaction bound"):
                hosted_release_ledger.fetch(state_dir, self._SERVICE)

    def test_history_receipt_hash_authority_and_service_are_verified(self) -> None:
        for mutation in ("hash", "authority", "service"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                state_dir = Path(temporary)
                state, current = self._commit(
                    state_dir=state_dir,
                    stage="canary",
                    decision="continue",
                    generation=0,
                )
                history = dict(current)
                history["triggerStage"] = "50"
                history.pop("receiptId")
                if mutation == "authority":
                    history["authority"] = "untrusted-plane"
                elif mutation == "service":
                    history["service"] = "other-service"
                history_id = hosted_release_ledger._receipt_id(history)
                history["receiptId"] = history_id
                if mutation == "hash":
                    history["verifiedAt"] = "2026-07-26T00:01:00Z"
                receipt_path = state_dir / "receipts" / f"{history_id}.json"
                receipt_path.write_text(
                    json.dumps(history, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                state["percent_50_receipt_id"] = history_id
                self._write_state(state_dir / f"{self._SERVICE}.state", state)
                with self.assertRaisesRegex(
                    RuntimeError,
                    "digest or ledger binding is invalid",
                ):
                    hosted_release_ledger.fetch(state_dir, self._SERVICE)

    def test_stackctl_readback_requires_fixed_stage_history_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            readback = hosted_release_ledger.commit(
                Path(temporary),
                {
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
                    "service": self._SERVICE,
                    "fromCandidateDigest": self._FROM_CANDIDATE,
                    "toCandidateDigest": self._TO_CANDIDATE,
                    "step": "0",
                    "stage": "canary",
                    "triggerStage": "canary",
                    "fromServiceFactoryOciDigest": self._FROM_CANDIDATE,
                    "toServiceFactoryOciDigest": self._TO_CANDIDATE,
                    "fromAppFactoryOciDigest": "sha256:" + ("1" * 64),
                    "toAppFactoryOciDigest": "sha256:" + ("1" * 64),
                    "decision": "continue",
                    "rollbackOutcome": "not_triggered",
                    "rollbackEvidence": {"triggered": False},
                    "candidateMaterialId": self._DIGEST,
                    **self._candidate(),
                    "expectedGeneration": 0,
                    "sloReadback": {"sampleCount": 100},
                    "postChecks": [],
                    "lastGoodCandidateDigest": self._FROM_CANDIDATE,
                    "verifiedAt": "2026-07-26T00:00:00Z",
                },
            )

        self.assertEqual(
            stackctl._validate_hosted_release_readback(
                readback,
                service=self._SERVICE,
            ),
            readback,
        )
        for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values():
            invalid = copy.deepcopy(readback)
            invalid["state"].pop(field)
            with self.subTest(missing=field), self.assertRaisesRegex(
                RuntimeError,
                "shape is not canonical",
            ):
                stackctl._validate_hosted_release_readback(
                    invalid,
                    service=self._SERVICE,
                )

        malformed = copy.deepcopy(readback)
        malformed["state"]["percent_50_receipt_id"] = "not-a-receipt"
        with self.assertRaisesRegex(RuntimeError, "history is invalid"):
            stackctl._validate_hosted_release_readback(
                malformed,
                service=self._SERVICE,
            )

        wrong_slot = copy.deepcopy(readback)
        wrong_slot["state"]["canary_receipt_id"] = ""
        wrong_slot["state"]["percent_50_receipt_id"] = wrong_slot["state"][
            "receipt_id"
        ]
        with self.assertRaisesRegex(RuntimeError, "not trigger-stage bound"):
            stackctl._validate_hosted_release_readback(
                wrong_slot,
                service=self._SERVICE,
            )

    def test_stackctl_cache_revalidates_history_before_local_write(self) -> None:
        with tempfile.TemporaryDirectory() as hosted_temporary:
            readback = hosted_release_ledger.commit(
                Path(hosted_temporary),
                {
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
                    "service": self._SERVICE,
                    "fromCandidateDigest": self._FROM_CANDIDATE,
                    "toCandidateDigest": self._TO_CANDIDATE,
                    "step": "0",
                    "stage": "canary",
                    "triggerStage": "canary",
                    "fromServiceFactoryOciDigest": self._FROM_CANDIDATE,
                    "toServiceFactoryOciDigest": self._TO_CANDIDATE,
                    "fromAppFactoryOciDigest": "sha256:" + ("1" * 64),
                    "toAppFactoryOciDigest": "sha256:" + ("1" * 64),
                    "decision": "continue",
                    "rollbackOutcome": "not_triggered",
                    "rollbackEvidence": {"triggered": False},
                    "candidateMaterialId": self._DIGEST,
                    **self._candidate(),
                    "expectedGeneration": 0,
                    "sloReadback": {},
                    "postChecks": [],
                    "lastGoodCandidateDigest": self._FROM_CANDIDATE,
                    "verifiedAt": "2026-07-26T00:00:00Z",
                },
            )
        invalid_state = dict(readback["state"])
        invalid_state.pop("percent_100_receipt_id")
        with tempfile.TemporaryDirectory() as cache_temporary:
            cache_dir = Path(cache_temporary)
            with (
                mock.patch.object(
                    stackctl,
                    "_release_state_dir",
                    return_value=cache_dir,
                ),
                self.assertRaisesRegex(RuntimeError, "shape is not canonical"),
            ):
                stackctl._cache_hosted_release_readback(
                    self._SERVICE,
                    invalid_state,
                    readback["receipt"],
                )
            self.assertFalse((cache_dir / f"{self._SERVICE}.state").exists())

    def test_stackctl_commit_uses_returned_hosted_readback_without_refetch(self) -> None:
        committed = {
            "state": {"receipt_id": "a" * 64},
            "receipt": {"receiptId": "a" * 64},
            "receiptRef": "receipt:hosted:" + "a" * 64,
        }
        cached_path = Path("/tmp/hosted-release-receipt.json")
        with (
            mock.patch.object(
                stackctl,
                "_run_hosted_release_ledger",
                return_value=committed,
            ) as run_hosted,
            mock.patch.object(
                stackctl,
                "_cache_hosted_release_readback",
                return_value=(committed["state"], cached_path),
            ) as cache_readback,
            mock.patch.object(
                stackctl,
                "utc_now",
                return_value="2026-07-26T00:00:00Z",
            ),
        ):
            result = stackctl._commit_hosted_release_transition(
                service=self._SERVICE,
                from_candidate_digest=self._FROM_CANDIDATE,
                to_candidate_digest=self._TO_CANDIDATE,
                step="5",
                stage="canary",
                decision="continue",
                candidate_material_id=self._DIGEST,
                expected_generation=0,
                receipt_id="unused",
                slo_readback={"sampleCount": 100},
                candidate_digests=self._candidate(),
                last_good_candidate_digest=self._FROM_CANDIDATE,
                post_deploy_checks=[],
                rollback_outcome="not_triggered",
                rollback_evidence={"triggered": False},
                from_service_factory_oci_digest=self._FROM_CANDIDATE,
                to_service_factory_oci_digest=self._TO_CANDIDATE,
                from_app_factory_oci_digest=self._FROM_CANDIDATE,
                to_app_factory_oci_digest=self._TO_CANDIDATE,
                prod_activation_admission=self._admission(),
            )

        self.assertEqual(result, (committed["state"], cached_path))
        self.assertEqual(run_hosted.call_count, 1)
        self.assertEqual(run_hosted.call_args.kwargs["action"], "commit")
        self.assertEqual(
            run_hosted.call_args.kwargs["request"]["rollbackEvidence"],
            {"triggered": False},
        )
        cache_readback.assert_called_once_with(
            self._SERVICE,
            committed["state"],
            committed["receipt"],
        )


if __name__ == "__main__":
    unittest.main()
