from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.ci import hosted_ci_timing_ledger as ledger
from quwoquan_ops.ci import sync_hosted_ci_timing_ledger as sync


def summary(*, status: str = "within_budget") -> dict[str, object]:
    return {
        "schema": "ci-timing-summary",
        "generatedAt": "2026-07-28T01:00:00Z",
        "workflow": {
            "gateKey": "07.mainline_auto_prod",
            "name": "07. Deploy To Prod (Controlled)",
            "title": "07. Deploy To Prod (Controlled)",
        },
        "workflowRunId": "42",
        "sourceGitSha": "a" * 40,
        "candidateDigest": "sha256:" + "b" * 64,
        "status": status,
        "timestamps": {
            "runCreatedAt": "2026-07-28T00:50:00Z",
            "candidateReadyAt": "2026-07-28T00:52:00Z",
            "approvalRequestedAt": "2026-07-28T00:53:00Z",
            "approvalApprovedAt": "2026-07-28T00:54:00Z",
            "prodFullyVerifiedAt": "2026-07-28T01:00:00Z",
        },
        "durations": {
            "queueSeconds": 10,
            "setupSeconds": 5,
            "executionSeconds": 500,
            "humanDecisionWaitSeconds": 30,
            "approvalWaitSeconds": 30,
            "calendarLeadTimeSeconds": 600,
            "machineCriticalPathSeconds": 570,
        },
        "budget": {
            "softSeconds": 600,
            "hardSeconds": 1800,
            "deltaFromSoftSeconds": 0,
            "deltaFromHardSeconds": -1200,
            "phaseSeconds": {},
        },
        "criticalPath": {
            "source": "github_run_calendar",
            "definition": "workflow run created_at to Prod verification",
            "seconds": 600,
        },
        "phases": [{"name": "candidate", "durationSeconds": 120}],
        "missingEvidence": [],
        "notes": ["official evidence"],
    }


def write_summary(path: Path, value: dict[str, object] | None = None) -> bytes:
    raw = (
        json.dumps(value or summary(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw


def exact_ref(character: str) -> tuple[str, str]:
    digest = "sha256:" + character * 64
    return f"ghcr.io/owner/repository/ci-timing-summary@{digest}", digest


class HostedCiTimingLedgerContractTest(unittest.TestCase):
    def test_append_only_authority_binds_exact_oci_and_queries_same_record(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            root = tmp_path / "hosted"
            ledger.initialize(root)
            path = tmp_path / "ci-timing-summary.json"
            raw = write_summary(path)
            value = ledger.validate_summary(json.loads(raw))
            ref, digest = exact_ref("c")
            record = ledger.build_record(value, raw, ref, digest)

            committed = ledger.bind(root, record)
            queried = ledger.query(root, "sha256:" + "b" * 64, "42")

            self.assertEqual(committed, record)
            self.assertEqual(queried, record)
            self.assertNotIn("schema", queried)
            self.assertEqual(
                queried["timingSummary"]["schema"], "ci-timing-summary"
            )
            self.assertEqual(queried["timingEvidenceRef"], ref)
            self.assertEqual(queried["timingEvidenceDigest"], digest)
            self.assertTrue(queried["timingSummaryDigest"].startswith("sha256:"))
            self.assertEqual(len(list(root.glob("records/*.json"))), 1)
            self.assertEqual(len(list(root.glob("by-run/42/*.ref"))), 1)

    def test_same_candidate_and_run_is_idempotent_but_never_overwritten(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hosted"
            ledger.initialize(root)
            raw = (json.dumps(summary(), sort_keys=True) + "\n").encode()
            ref, digest = exact_ref("c")
            first = ledger.build_record(summary(), raw, ref, digest)
            self.assertEqual(ledger.bind(root, first), ledger.bind(root, first))

            other_ref, other_digest = exact_ref("d")
            conflicting = ledger.build_record(
                summary(), raw, other_ref, other_digest
            )
            with self.assertRaisesRegex(
                RuntimeError, "append-only binding conflicts"
            ):
                ledger.bind(root, conflicting)

    def test_missing_hosted_authority_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            raw = (json.dumps(summary(), sort_keys=True) + "\n").encode()
            ref, digest = exact_ref("c")
            record = ledger.build_record(summary(), raw, ref, digest)

            with self.assertRaisesRegex(RuntimeError, "authority is missing"):
                ledger.bind(Path(temporary) / "not-provisioned", record)

    def test_non_exact_ref_and_noncanonical_summary_are_rejected(self) -> None:
        raw = (json.dumps(summary(), sort_keys=True) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "exact GHCR OCI digest ref"):
            ledger.build_record(
                summary(),
                raw,
                "ghcr.io/owner/repository/ci-timing-summary:latest",
                "sha256:" + "c" * 64,
            )

        old = summary()
        old["schema" + "Version"] = "old"
        with self.assertRaisesRegex(ValueError, "non-canonical shape"):
            ledger.validate_summary(old)

    def test_historical_incomplete_summary_is_archivable_without_fabrication(
        self,
    ) -> None:
        value = summary(status="historical_incomplete")
        timestamps = value["timestamps"]
        durations = value["durations"]
        assert isinstance(timestamps, dict)
        assert isinstance(durations, dict)
        timestamps["approvalRequestedAt"] = None
        durations["approvalWaitSeconds"] = None
        value["missingEvidence"] = [
            "timestamps.approvalRequestedAt",
            "durations.approvalWaitSeconds",
        ]
        raw = (json.dumps(value, sort_keys=True) + "\n").encode()
        ref, digest = exact_ref("c")

        record = ledger.build_record(value, raw, ref, digest)

        self.assertEqual(
            record["timingSummary"]["status"], "historical_incomplete"
        )
        self.assertIsNone(
            record["timingSummary"]["timestamps"]["approvalRequestedAt"]
        )
        self.assertIsNone(
            record["timingSummary"]["durations"]["approvalWaitSeconds"]
        )

    def test_failure_path_without_candidate_cannot_bind_to_hosted_authority(
        self,
    ) -> None:
        value = summary(status="historical_incomplete")
        value["candidateDigest"] = None
        value["missingEvidence"] = ["candidateDigest"]

        with self.assertRaisesRegex(ValueError, "candidateDigest must be sha256"):
            ledger.validate_summary(value)

    def test_remote_bind_requires_independent_query_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ci-timing-summary.json"
            raw = write_summary(path)
            ref, digest = exact_ref("c")
            expected = ledger.build_record(summary(), raw, ref, digest)

            with mock.patch.object(
                sync, "_remote_action", side_effect=[expected, expected]
            ) as remote:
                result = sync.bind_and_readback(path, ref, digest)

        self.assertEqual(result, expected)
        self.assertEqual(
            [call.kwargs["action"] for call in remote.call_args_list],
            ["bind", "query"],
        )

    def test_remote_bind_rejects_mismatched_query_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ci-timing-summary.json"
            raw = write_summary(path)
            ref, digest = exact_ref("c")
            expected = ledger.build_record(summary(), raw, ref, digest)
            different = dict(expected)
            different["timingEvidenceDigest"] = "sha256:" + "d" * 64

            with mock.patch.object(
                sync, "_remote_action", side_effect=[expected, different]
            ), self.assertRaisesRegex(RuntimeError, "query does not match"):
                sync.bind_and_readback(path, ref, digest)


if __name__ == "__main__":
    unittest.main()
