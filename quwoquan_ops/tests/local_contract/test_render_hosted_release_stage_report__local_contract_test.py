# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.ci import render_hosted_release_stage_report as stage_report
from quwoquan_ops.ci import render_release_lifecycle_receipts as lifecycle


class HostedReleaseStageReportTest(unittest.TestCase):
    service = "gateway"
    candidate = "sha256:" + "c" * 64
    from_candidate = "sha256:" + "b" * 64
    artifact = "sha256:" + "d" * 64

    def _manifest(self) -> dict:
        return {
            "status": "deployable",
            "candidateId": self.candidate,
            "artifactDigest": self.artifact,
            "source": {
                "gitSha": "a" * 40,
                "treeDigest": "sha1:" + "e" * 40,
            },
        }

    def _receipt(
        self,
        stage: str,
        *,
        decision: str = "continue",
        rollback_outcome: str = "not_triggered",
        trigger_stage: str | None = None,
        candidate: str | None = None,
        artifact: str | None = None,
    ) -> dict:
        receipt = {
            "schema": lifecycle.HOSTED_RECEIPT_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "service": self.service,
            "fromCandidateDigest": self.from_candidate,
            "toCandidateDigest": candidate or self.candidate,
            "step": {"canary": 0, "5": 5, "20": 20, "50": 50, "100": 100}[stage],
            "stage": stage,
            "triggerStage": trigger_stage or stage,
            "fromReleaseEvidenceRef": (
                "ghcr.io/owner/repo/release-evidence@" + self.from_candidate
            ),
            "toReleaseEvidenceRef": (
                "ghcr.io/owner/repo/release-evidence@" + self.candidate
            ),
            "fromImageTransportTag": "sha-from",
            "toImageTransportTag": "sha-to",
            "decision": decision,
            "rollbackOutcome": rollback_outcome,
            "rollbackEvidence": (
                {
                    "triggered": True,
                    "startedAt": "2026-07-28T00:08:00Z",
                    "endedAt": "2026-07-28T00:09:00Z",
                    "durationMs": 60_000,
                    "postChecks": [
                        {
                            "name": "rollback-health",
                            "status": (
                                "passed"
                                if rollback_outcome == "rolled_back"
                                else "failed"
                            ),
                            "receiptDigest": "sha256:" + "8" * 64,
                        }
                    ],
                }
                if rollback_outcome in {"rolled_back", "rollback_failed"}
                else {"triggered": False}
            ),
            "artifactDigest": artifact or self.artifact,
            "imageDigest": "sha256:" + "1" * 64,
            "configDigest": "sha256:" + "2" * 64,
            "contractGraphDigest": "sha256:" + "3" * 64,
            "adapterDigest": "sha256:" + "4" * 64,
            "expectedGeneration": 1,
            "committedGeneration": 2,
            "sloReadback": {"status": "passed"},
            "postChecks": [
                {
                    "name": "ready",
                    "status": "passed",
                    "receiptDigest": "sha256:" + "5" * 64,
                }
            ],
            "lastGoodCandidateDigest": (
                self.candidate if stage == "100" else self.from_candidate
            ),
            "verifiedAt": "2026-07-28T00:10:00Z",
            "receiptId": "",
        }
        receipt["receiptId"] = lifecycle._receipt_id(receipt)
        return receipt

    def _readback(self, receipt: dict) -> dict:
        return {
            "schema": lifecycle.HOSTED_RECEIPT_READBACK_SCHEMA,
            "authority": lifecycle.HOSTED_AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt['receiptId']}",
        }

    def _rollback_receipt(self, stage: str, *, failed: bool = False) -> dict:
        if failed:
            receipt = self._receipt(
                stage,
                decision="rollback_failed",
                rollback_outcome="rollback_failed",
            )
            receipt["lastGoodCandidateDigest"] = self.from_candidate
        else:
            receipt = self._receipt(
                "100",
                decision="rolled_back",
                rollback_outcome="rolled_back",
                trigger_stage=stage,
            )
            receipt.update(
                {
                    "fromCandidateDigest": self.candidate,
                    "toCandidateDigest": self.from_candidate,
                    "fromReleaseEvidenceRef": (
                        "ghcr.io/owner/repo/release-evidence@" + self.candidate
                    ),
                    "toReleaseEvidenceRef": (
                        "ghcr.io/owner/repo/release-evidence@"
                        + self.from_candidate
                    ),
                    "lastGoodCandidateDigest": self.from_candidate,
                }
            )
        receipt["receiptId"] = lifecycle._receipt_id(receipt)
        return receipt

    def _write(self, path: Path, payload: dict) -> Path:
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_replayed_stage_reports_can_seal_the_existing_prod_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = {}
            readbacks = {}
            with patch.object(stage_report, "validate_manifest"):
                for stage in lifecycle.STAGES:
                    readback = self._readback(self._receipt(stage))
                    report = stage_report.render(
                        manifest=self._manifest(),
                        stage_readback=readback,
                        stage=stage,
                        service=self.service,
                    )
                    reports[stage] = (
                        self._write(root / f"{stage}-report.json", report),
                        report,
                    )
                    readbacks[stage] = (
                        self._write(root / f"{stage}-readback.json", readback),
                        readback,
                    )
            with patch.object(lifecycle, "validate_manifest"):
                sealed = lifecycle.render_prod_outcome(
                    manifest=self._manifest(),
                    service=self.service,
                    from_candidate_digest=self.from_candidate,
                    reports=reports,
                    readbacks=readbacks,
                    archive_prefix="evidence/raw/prod/outcome",
                    hard_deadline_epoch=int(
                        lifecycle.dt.datetime(
                            2026,
                            7,
                            28,
                            0,
                            30,
                            tzinfo=lifecycle.dt.timezone.utc,
                        ).timestamp()
                    ),
                    rollback_budget_seconds=300,
                )

        self.assertEqual(sealed["environment"]["status"], "passed")
        self.assertEqual(sealed["rollout"]["status"], "passed")
        self.assertEqual(sealed["rollback"]["status"], "not_triggered")
        self.assertTrue(reports["100"][1]["replayed"])
        self.assertEqual(
            reports["100"][1]["projectionPurpose"], "terminal-sealing-only"
        )
        self.assertEqual(
            reports["100"][1]["sourceAuthority"], lifecycle.HOSTED_AUTHORITY
        )

    def test_hosted_rollback_receipt_replays_without_a_local_stage_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gray_receipt = self._receipt("canary")
            rollback_receipt = self._rollback_receipt("5")
            reports = {}
            readbacks = {}
            with patch.object(stage_report, "validate_manifest"):
                for stage, receipt in (
                    ("canary", gray_receipt),
                    ("5", rollback_receipt),
                ):
                    readback = self._readback(receipt)
                    report = stage_report.render(
                        manifest=self._manifest(),
                        stage_readback=readback,
                        stage=stage,
                        service=self.service,
                    )
                    reports[stage] = (
                        self._write(root / f"{stage}-report.json", report),
                        report,
                    )
                    readbacks[stage] = (
                        self._write(root / f"{stage}-readback.json", readback),
                        readback,
                    )
            with patch.object(lifecycle, "validate_manifest"):
                sealed = lifecycle.render_prod_outcome(
                    manifest=self._manifest(),
                    service=self.service,
                    from_candidate_digest=self.from_candidate,
                    reports=reports,
                    readbacks=readbacks,
                    archive_prefix="evidence/raw/prod/outcome",
                    hard_deadline_epoch=int(
                        lifecycle.dt.datetime(
                            2026,
                            7,
                            28,
                            0,
                            30,
                            tzinfo=lifecycle.dt.timezone.utc,
                        ).timestamp()
                    ),
                    rollback_budget_seconds=300,
                )

        replay = reports["5"][1]
        self.assertEqual(replay["terminalStage"], "100")
        self.assertEqual(replay["rolloutDecision"], "rollback")
        self.assertEqual(replay["rollback"]["durationMs"], 60_000)
        self.assertEqual(replay["rollbackPostChecks"][0]["exitCode"], 0)
        self.assertEqual(sealed["rollout"]["status"], "failed")
        self.assertEqual(sealed["rollback"]["status"], "rolled_back")

    def test_hosted_rollback_failure_projects_its_real_terminal_evidence(self) -> None:
        receipt = self._rollback_receipt("5", failed=True)
        with patch.object(stage_report, "validate_manifest"):
            report = stage_report.render(
                manifest=self._manifest(),
                stage_readback=self._readback(receipt),
                stage="5",
                service=self.service,
            )

        self.assertNotEqual(report["exitCode"], 0)
        self.assertEqual(report["terminalStage"], "5")
        self.assertEqual(report["rollback"]["durationMs"], 60_000)
        self.assertEqual(report["rollbackPostChecks"][0]["exitCode"], 1)

    def test_hosted_rollback_replay_rejects_budget_or_stable_candidate_drift(self) -> None:
        over_budget = self._rollback_receipt("5")
        over_budget["rollbackEvidence"]["durationMs"] = 300_001
        over_budget["receiptId"] = lifecycle._receipt_id(over_budget)
        stable_drift = self._rollback_receipt("5")
        stable_drift["lastGoodCandidateDigest"] = "sha256:" + "9" * 64
        stable_drift["receiptId"] = lifecycle._receipt_id(stable_drift)

        with patch.object(stage_report, "validate_manifest"):
            for receipt in (over_budget, stable_drift):
                with self.subTest(receipt=receipt["receiptId"]), self.assertRaises(
                    ValueError
                ):
                    stage_report.render(
                        manifest=self._manifest(),
                        stage_readback=self._readback(receipt),
                        stage="5",
                        service=self.service,
                    )

    def test_pause_rollback_and_failed_postcheck_cannot_project_success(self) -> None:
        cases = (
            self._receipt("5", decision="pause"),
            self._receipt("5", rollback_outcome="rolled_back"),
            self._receipt("5"),
        )
        cases[2]["postChecks"][0]["status"] = "failed"
        cases[2]["receiptId"] = lifecycle._receipt_id(cases[2])
        with patch.object(stage_report, "validate_manifest"):
            for receipt in cases:
                with self.subTest(
                    decision=receipt["decision"],
                    rollback=receipt["rollbackOutcome"],
                ), self.assertRaises(ValueError):
                    stage_report.render(
                        manifest=self._manifest(),
                        stage_readback=self._readback(receipt),
                        stage="5",
                        service=self.service,
                    )

    def test_candidate_artifact_stage_and_trigger_drift_are_rejected(self) -> None:
        mismatches = (
            self._receipt("canary", candidate="sha256:" + "6" * 64),
            self._receipt("canary", artifact="sha256:" + "7" * 64),
            self._receipt("5"),
            self._receipt("canary", trigger_stage="100"),
        )
        with patch.object(stage_report, "validate_manifest"):
            for receipt in mismatches:
                with self.subTest(
                    stage=receipt["stage"], trigger=receipt["triggerStage"]
                ), self.assertRaises(ValueError):
                    stage_report.render(
                        manifest=self._manifest(),
                        stage_readback=self._readback(receipt),
                        stage="canary",
                        service=self.service,
                    )

    def test_hosted_readback_authority_and_receipt_identity_are_reused(self) -> None:
        receipt = self._receipt("canary")
        readback = self._readback(receipt)
        readback["authority"] = "runner-local"
        with patch.object(stage_report, "validate_manifest"), self.assertRaisesRegex(
            ValueError, "readback shape"
        ):
            stage_report.render(
                manifest=self._manifest(),
                stage_readback=readback,
                stage="canary",
                service=self.service,
            )

    def test_cli_writes_the_canonical_replay_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self._write(root / "manifest.json", self._manifest())
            readback = self._write(
                root / "readback.json",
                self._readback(self._receipt("canary")),
            )
            output = root / "stage-report.json"
            argv = [
                "render_hosted_release_stage_report.py",
                "--manifest",
                str(manifest),
                "--stage-readback",
                str(readback),
                "--stage",
                "canary",
                "--service",
                self.service,
                "--output",
                str(output),
            ]
            with patch.object(stage_report, "validate_manifest"), patch.object(
                sys, "argv", argv
            ), patch("builtins.print"):
                result = stage_report.main()
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertTrue(payload["replayed"])
        self.assertEqual(payload["rolloutDecision"], "continue")
        self.assertEqual(payload["sourceAuthority"], lifecycle.HOSTED_AUTHORITY)

    def test_tool_source_has_no_contract_version_identity(self) -> None:
        source = (
            Path(__file__).resolve().parents[3]
            / "quwoquan_ops/ci/render_hosted_release_stage_report.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("schemaVersion", "contractVersion", "registryRevision"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
