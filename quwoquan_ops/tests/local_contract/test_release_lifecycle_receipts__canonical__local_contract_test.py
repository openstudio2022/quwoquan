# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.ci import render_release_lifecycle_receipts as lifecycle
from quwoquan_ops.tests.local_contract.rollout_stage_promotion_evidence_test_support import (
    promotion_evidence,
)


def digest(character: str) -> str:
    return "sha256:" + character * 64


class ReleaseLifecycleReceiptsTest(unittest.TestCase):
    candidate = digest("c")
    artifact = digest("a")
    from_candidate = digest("f")
    service = "prod-stack"

    def _manifest(self, status: str) -> dict:
        return {
            "status": status,
            "candidateId": self.candidate,
            "artifactDigest": self.artifact,
            "source": {
                "gitSha": "b" * 40,
                "treeDigest": "sha1:" + "d" * 40,
            },
            "environmentReceipts": (
                {environment: {} for environment in ("alpha", "beta", "gamma")}
                if status == "candidate-ready"
                else {environment: {} for environment in ("alpha", "beta", "gamma")}
            ),
        }

    def _hosted_receipt(
        self,
        *,
        stage: str = "100",
        decision: str = "continue",
        rollback_outcome: str = "not_triggered",
        from_candidate: str | None = None,
        to_candidate: str | None = None,
        last_good: str | None = None,
        generation: int = 3,
        trigger_stage: str | None = None,
    ) -> dict:
        from_value = from_candidate or self.from_candidate
        to_value = to_candidate or self.candidate
        receipt = {
            "schema": lifecycle.HOSTED_RECEIPT_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "service": self.service,
            "fromCandidateDigest": from_value,
            "toCandidateDigest": to_value,
            "step": {"canary": "0", "5": "5", "20": "20", "50": "50", "100": "100"}[
                stage
            ],
            "stage": stage,
            "triggerStage": trigger_stage or stage,
            "fromReleaseEvidenceRef": (
                f"ghcr.io/owner/repo/release-artifact@{from_value}"
            ),
            "toReleaseEvidenceRef": (
                f"ghcr.io/owner/repo/release-artifact@{to_value}"
            ),
            "fromImageTransportTag": "sha-source",
            "toImageTransportTag": "sha-target",
            "decision": decision,
            "rollbackOutcome": rollback_outcome,
            "rollbackEvidence": (
                {
                    "triggered": True,
                    "startedAt": "2026-07-28T00:03:00Z",
                    "endedAt": "2026-07-28T00:04:00Z",
                    "durationMs": 60_000,
                    "postChecks": [
                        {
                            "name": "rollback-health",
                            "status": (
                                "passed"
                                if rollback_outcome == "rolled_back"
                                else "failed"
                            ),
                            "receiptDigest": digest("6"),
                        }
                    ],
                }
                if rollback_outcome in {"rolled_back", "rollback_failed"}
                else {"triggered": False}
            ),
            "artifactDigest": self.artifact,
            "imageDigest": digest("1"),
            "configDigest": digest("2"),
            "contractGraphDigest": digest("3"),
            "adapterDigest": digest("4"),
            "expectedGeneration": generation - 1,
            "committedGeneration": generation,
            "sloReadback": {
                "sampleCount": 100,
                **(
                    {
                        "promotionEvidence": promotion_evidence(
                            candidate_id=to_value,
                            artifact_digest=self.artifact,
                            stage=trigger_stage or stage,
                        )
                    }
                    if decision == "continue"
                    else {}
                ),
            },
            "postChecks": [
                {
                    "name": "health",
                    "status": "passed",
                    "receiptDigest": digest("5"),
                }
            ],
            "lastGoodCandidateDigest": last_good or to_value,
            "verifiedAt": "2026-07-28T00:05:00Z",
        }
        receipt["receiptId"] = lifecycle._receipt_id(receipt)
        return receipt

    def _receipt_readback(self, receipt: dict) -> dict:
        return {
            "schema": lifecycle.HOSTED_RECEIPT_READBACK_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt['receiptId']}",
        }

    def _ledger_readback(self, receipt: dict) -> dict:
        state = {
            "schema": lifecycle.HOSTED_STATE_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "service": self.service,
            "from_candidate_digest": receipt["fromCandidateDigest"],
            "to_candidate_digest": receipt["toCandidateDigest"],
            "step": receipt["step"],
            "stage": receipt["stage"],
            "trigger_stage": receipt["triggerStage"],
            "from_release_evidence_ref": receipt["fromReleaseEvidenceRef"],
            "to_release_evidence_ref": receipt["toReleaseEvidenceRef"],
            "from_image_transport_tag": receipt["fromImageTransportTag"],
            "to_image_transport_tag": receipt["toImageTransportTag"],
            "decision": receipt["decision"],
            "rollback_outcome": receipt["rollbackOutcome"],
            "artifact_digest": receipt["artifactDigest"],
            "image_digest": receipt["imageDigest"],
            "config_digest": receipt["configDigest"],
            "contract_graph_digest": receipt["contractGraphDigest"],
            "adapter_digest": receipt["adapterDigest"],
            "last_good_candidate_digest": receipt["lastGoodCandidateDigest"],
            "canary_receipt_id": "",
            "percent_5_receipt_id": "",
            "percent_20_receipt_id": "",
            "percent_50_receipt_id": "",
            "percent_100_receipt_id": "",
            "generation": str(receipt["committedGeneration"]),
            "receipt_id": receipt["receiptId"],
            "updated_at": receipt["verifiedAt"],
        }
        state[
            lifecycle.hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS[
                receipt["triggerStage"]
            ]
        ] = receipt["receiptId"]
        return {
            "schema": lifecycle.HOSTED_READBACK_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "state": state,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt['receiptId']}",
        }

    @staticmethod
    def _write(path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_rollback_readiness_requires_three_real_hosted_evidence_classes(self) -> None:
        current = self._hosted_receipt(
            from_candidate=digest("e"),
            to_candidate=self.from_candidate,
            last_good=self.from_candidate,
        )
        drill = self._hosted_receipt(
            decision="rolled_back",
            rollback_outcome="rolled_back",
            from_candidate=digest("9"),
            to_candidate=self.from_candidate,
            last_good=self.from_candidate,
            generation=2,
        )
        backup = {
            "schema": "quwoquan-prod-backup-recovery-validation",
            "status": "ok",
            "planDigest": digest("6"),
            "receiptDigest": digest("7"),
            "issues": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current_path = self._write(
                root / "current.json", self._ledger_readback(current)
            )
            drill_path = self._write(
                root / "drill.json", self._receipt_readback(drill)
            )
            backup_path = self._write(root / "backup.json", backup)
            with patch.object(lifecycle, "validate_manifest"):
                receipt = lifecycle.render_rollback_readiness(
                    manifest=self._manifest("candidate-ready"),
                    service=self.service,
                    from_candidate_digest=self.from_candidate,
                    current_ledger_path=current_path,
                    current_ledger=json.loads(current_path.read_text()),
                    rollback_drill_path=drill_path,
                    rollback_drill=json.loads(drill_path.read_text()),
                    backup_validation_path=backup_path,
                    backup_validation=backup,
                    archive_prefix="evidence/raw/prod/readiness",
                    rollback_drill_max_age_seconds=2_592_000,
                )
        self.assertEqual(receipt["schema"], "release-rollback-receipt")
        self.assertEqual(receipt["status"], "ready")
        self.assertEqual(receipt["candidateId"], self.candidate)

    def test_readiness_rejects_a_non_recovery_drill(self) -> None:
        current = self._hosted_receipt(
            to_candidate=self.from_candidate, last_good=self.from_candidate
        )
        drill = self._hosted_receipt()
        backup = {
            "schema": "quwoquan-prod-backup-recovery-validation",
            "status": "ok",
            "planDigest": digest("6"),
            "receiptDigest": digest("7"),
            "issues": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current_path = self._write(
                root / "current.json", self._ledger_readback(current)
            )
            drill_path = self._write(
                root / "drill.json", self._receipt_readback(drill)
            )
            backup_path = self._write(root / "backup.json", backup)
            with patch.object(lifecycle, "validate_manifest"), self.assertRaisesRegex(
                ValueError, "does not recover the current stable candidate"
            ):
                lifecycle.render_rollback_readiness(
                    manifest=self._manifest("candidate-ready"),
                    service=self.service,
                    from_candidate_digest=self.from_candidate,
                    current_ledger_path=current_path,
                    current_ledger=json.loads(current_path.read_text()),
                    rollback_drill_path=drill_path,
                    rollback_drill=json.loads(drill_path.read_text()),
                    backup_validation_path=backup_path,
                    backup_validation=backup,
                    archive_prefix="evidence/raw/prod/readiness",
                    rollback_drill_max_age_seconds=2_592_000,
                )

    def _stage_pair(
        self,
        root: Path,
        *,
        stage: str,
        decision: str = "continue",
        rollback_outcome: str = "not_triggered",
    ) -> tuple[tuple[Path, dict], tuple[Path, dict]]:
        if rollback_outcome == "rolled_back":
            receipt = self._hosted_receipt(
                stage="100",
                trigger_stage=stage,
                decision="rolled_back",
                rollback_outcome="rolled_back",
                from_candidate=self.candidate,
                to_candidate=self.from_candidate,
                last_good=self.from_candidate,
            )
        else:
            receipt = self._hosted_receipt(
                stage=stage,
                decision=decision,
                rollback_outcome=rollback_outcome,
                from_candidate=self.from_candidate,
                to_candidate=self.candidate,
                last_good=(
                    self.candidate
                    if stage == "100" and rollback_outcome == "not_triggered"
                    else self.from_candidate
                ),
            )
        failed = rollback_outcome in {"rolled_back", "rollback_failed"}
        report = {
            "command": "deploy",
            "target": "prod-hosted",
            "rolloutStage": stage,
            "triggerStage": stage,
            "terminalStage": receipt["stage"],
            "rolloutDecision": "rollback" if failed else "continue",
            "artifactDigest": self.artifact,
            "candidateId": self.candidate,
            "releaseReceiptId": receipt["receiptId"],
            "releaseReceiptRef": f"receipt:hosted:{receipt['receiptId']}",
            "releaseReceiptAuthority": lifecycle.HOSTED_AUTHORITY,
            "exitCode": 11 if failed else 0,
            "dryRun": False,
            "postDeployFailures": ["SLO"] if failed else [],
            "rollbackPostChecks": [{"exitCode": 0}] if rollback_outcome == "rolled_back" else [],
            "rollback": {
                "triggered": failed,
                "startedAt": "2026-07-28T00:05:00Z" if failed else "",
                "endedAt": "2026-07-28T00:06:00Z" if failed else "",
                "durationMs": 60_000 if failed else 0,
            },
        }
        report_path = self._write(root / f"{stage}-report.json", report)
        readback = self._receipt_readback(receipt)
        readback_path = self._write(root / f"{stage}-readback.json", readback)
        return (report_path, report), (readback_path, readback)

    def test_full_rollout_seals_released_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = {}
            readbacks = {}
            for stage in lifecycle.STAGES:
                reports[stage], readbacks[stage] = self._stage_pair(root, stage=stage)
            with patch.object(lifecycle, "validate_manifest"):
                result = lifecycle.render_prod_outcome(
                    manifest=self._manifest("deployable"),
                    service=self.service,
                    from_candidate_digest=self.from_candidate,
                    reports=reports,
                    readbacks=readbacks,
                    archive_prefix="evidence/raw/prod/outcome",
                    hard_deadline_epoch=int(
                        lifecycle.dt.datetime(
                            2026, 7, 28, 0, 30, tzinfo=lifecycle.dt.timezone.utc
                        ).timestamp()
                    ),
                    rollback_budget_seconds=300,
                )
        self.assertEqual(result["environment"]["status"], "passed")
        self.assertEqual(result["rollout"]["status"], "passed")
        self.assertEqual(result["rollback"]["status"], "not_triggered")

    def test_successful_automatic_rollback_is_not_released(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = {}
            readbacks = {}
            reports["canary"], readbacks["canary"] = self._stage_pair(
                root, stage="canary"
            )
            reports["5"], readbacks["5"] = self._stage_pair(root, stage="5")
            reports["20"], readbacks["20"] = self._stage_pair(root, stage="20")
            reports["50"], readbacks["50"] = self._stage_pair(
                root, stage="50", rollback_outcome="rolled_back"
            )
            with patch.object(lifecycle, "validate_manifest"):
                result = lifecycle.render_prod_outcome(
                    manifest=self._manifest("deployable"),
                    service=self.service,
                    from_candidate_digest=self.from_candidate,
                    reports=reports,
                    readbacks=readbacks,
                    archive_prefix="evidence/raw/prod/outcome",
                    hard_deadline_epoch=int(
                        lifecycle.dt.datetime(
                            2026, 7, 28, 0, 30, tzinfo=lifecycle.dt.timezone.utc
                        ).timestamp()
                    ),
                    rollback_budget_seconds=300,
                )
        self.assertEqual(result["environment"]["status"], "passed")
        self.assertEqual(result["rollout"]["status"], "failed")
        self.assertEqual(result["rollback"]["status"], "rolled_back")

    def test_rollback_failure_is_terminal_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report, readback = self._stage_pair(
                root,
                stage="canary",
                decision="rollback_failed",
                rollback_outcome="rollback_failed",
            )
            with patch.object(lifecycle, "validate_manifest"):
                result = lifecycle.render_prod_outcome(
                    manifest=self._manifest("deployable"),
                    service=self.service,
                    from_candidate_digest=self.from_candidate,
                    reports={"canary": report},
                    readbacks={"canary": readback},
                    archive_prefix="evidence/raw/prod/outcome",
                    hard_deadline_epoch=int(
                        lifecycle.dt.datetime(
                            2026, 7, 28, 0, 30, tzinfo=lifecycle.dt.timezone.utc
                        ).timestamp()
                    ),
                    rollback_budget_seconds=300,
                )
        self.assertEqual(result["environment"]["status"], "failed")
        self.assertEqual(result["rollout"]["status"], "failed")
        self.assertEqual(result["rollback"]["status"], "rollback_failed")

    def test_rollback_over_300_seconds_cannot_seal_terminal_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report, readback = self._stage_pair(
                root,
                stage="canary",
                rollback_outcome="rolled_back",
            )
            report_path, report_payload = report
            report_payload["rollback"]["durationMs"] = 300_001
            self._write(report_path, report_payload)
            with patch.object(lifecycle, "validate_manifest"), self.assertRaisesRegex(
                ValueError, "300-second budget"
            ):
                lifecycle.render_prod_outcome(
                    manifest=self._manifest("deployable"),
                    service=self.service,
                    from_candidate_digest=self.from_candidate,
                    reports={"canary": (report_path, report_payload)},
                    readbacks={"canary": readback},
                    archive_prefix="evidence/raw/prod/outcome",
                    hard_deadline_epoch=int(
                        lifecycle.dt.datetime(
                            2026, 7, 28, 0, 30, tzinfo=lifecycle.dt.timezone.utc
                        ).timestamp()
                    ),
                    rollback_budget_seconds=300,
                )

    def test_missing_full_stage_cannot_be_reported_as_released(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report, readback = self._stage_pair(root, stage="canary")
            with patch.object(lifecycle, "validate_manifest"), self.assertRaisesRegex(
                ValueError, "full rollout evidence is incomplete"
            ):
                lifecycle.render_prod_outcome(
                    manifest=self._manifest("deployable"),
                    service=self.service,
                    from_candidate_digest=self.from_candidate,
                    reports={"canary": report},
                    readbacks={"canary": readback},
                    archive_prefix="evidence/raw/prod/outcome",
                    hard_deadline_epoch=int(
                        lifecycle.dt.datetime(
                            2026, 7, 28, 0, 30, tzinfo=lifecycle.dt.timezone.utc
                        ).timestamp()
                    ),
                    rollback_budget_seconds=300,
                )


if __name__ == "__main__":
    unittest.main()
