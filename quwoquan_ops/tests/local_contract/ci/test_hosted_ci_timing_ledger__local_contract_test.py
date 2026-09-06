# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.ci import hosted_ci_timing_ledger as ledger
from quwoquan_ops.ci import promotion_timing_ratchet as ratchet
from quwoquan_ops.ci import render_ci_timing_summary as renderer
from quwoquan_ops.ci import sync_hosted_ci_timing_ledger as sync


POLICY_DIGEST = "sha256:" + "1" * 64
WORKFLOW_DIGEST = "sha256:" + "2" * 64


def diagnostic_summary(*, status: str = "within_budget") -> dict[str, object]:
    return {
        "schema": "ci-timing-summary",
        "generatedAt": "2026-07-28T01:00:00Z",
        "workflow": {
            "gateKey": "07.stable_tag_prod",
            "name": "07. Deploy To Prod (Controlled)",
            "title": "07. Deploy To Prod (Controlled)",
        },
        "workflowRunId": "42",
        "sourceGitSha": "a" * 40,
        "candidateDigest": "sha256:" + "b" * 64,
        "status": status,
        "outcomePolicy": {
            "functional": "pass",
            "telemetryClassification": "attempted",
            "timing": "PASS",
        },
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
            "policy": "release_sla",
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


def promotion_sample(
    *,
    observation_id: str = "delivery-1",
    event_id: str = "event-1",
    ready: datetime | None = None,
    run_attempt: int = 1,
    classification: str = "success",
) -> dict[str, object]:
    ready = ready or datetime(2026, 7, 28, tzinfo=timezone.utc)
    readback = ready + timedelta(seconds=240)
    return ratchet.make_sample(
        observation_id=observation_id,
        event_id=event_id,
        repository="owner/repository",
        workflow_run_id="42",
        run_attempt=run_attempt,
        head_sha="a" * 40,
        base_sha="b" * 40,
        first_attempt_at=(ready - timedelta(seconds=10)).isoformat(),
        promotion_ready_at=ready.isoformat(),
        observed_at=readback.isoformat(),
        main_readback_at=readback.isoformat(),
        classification=classification,
        evidence_complete=True,
        policy_digest=POLICY_DIGEST,
        workflow_digest=WORKFLOW_DIGEST,
    )


def write_json(path: Path, value: dict[str, object]) -> bytes:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def exact_ref(artifact: str, character: str) -> tuple[str, str]:
    digest = "sha256:" + character * 64
    return f"ghcr.io/owner/repository/{artifact}@{digest}", digest


class HostedCiTimingLedgerContractTest(unittest.TestCase):
    def test_append_only_sample_authority_queries_observation_event_and_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            root = tmp_path / "hosted"
            ledger.initialize(root)
            path = tmp_path / "promotion-sample.json"
            raw = write_json(path, promotion_sample())
            value = ledger.validate_promotion_sample(json.loads(raw))
            ref, digest = exact_ref("promotion-timing-sample", "c")
            record = ledger.build_sample_record(value, raw, ref, digest)

            committed = ledger.bind(root, record)
            queried = ledger.query_sample(root, "delivery-1")
            event = ledger.query_event(root, "event-1")
            ranged = ledger.query_range(root, "2026-07-28T00:00:00Z", "2026-07-29T00:00:00Z")

            self.assertEqual(committed, record)
            self.assertEqual(queried, record)
            self.assertEqual(event["records"], [record])
            self.assertEqual(ranged["samples"], [value])
            self.assertEqual(record["recordKind"], "promotion_sample")
            self.assertEqual(len(list(root.glob("records/*.json"))), 1)

    def test_same_observation_is_idempotent_but_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hosted"
            ledger.initialize(root)
            value = promotion_sample()
            raw = (json.dumps(value, sort_keys=True) + "\n").encode()
            ref, digest = exact_ref("promotion-timing-sample", "c")
            first = ledger.build_sample_record(value, raw, ref, digest)
            self.assertEqual(ledger.bind(root, first), ledger.bind(root, first))

            other_ref, other_digest = exact_ref("promotion-timing-sample", "d")
            conflicting = ledger.build_sample_record(value, raw, other_ref, other_digest)
            with self.assertRaisesRegex(RuntimeError, "append-only binding conflicts"):
                ledger.bind(root, conflicting)

    def test_same_event_keeps_multiple_attempt_observations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hosted"
            ledger.initialize(root)
            for attempt in (1, 2):
                value = promotion_sample(
                    observation_id=f"delivery-{attempt}",
                    event_id="event-1",
                    run_attempt=attempt,
                )
                raw = (json.dumps(value, sort_keys=True) + "\n").encode()
                ref, digest = exact_ref("promotion-timing-sample", str(attempt + 1))
                ledger.bind(root, ledger.build_sample_record(value, raw, ref, digest))
            event = ledger.query_event(root, "event-1")
            self.assertEqual([item["runAttempt"] for item in event["records"]], [1, 2])

    def test_range_query_rejects_symlinked_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "hosted"
            ledger.initialize(root)
            records = root / "records"
            records.mkdir()
            target = Path(temporary) / "foreign.json"
            target.write_text("{}", encoding="utf-8")
            (records / ("f" * 64 + ".json")).symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, "records root is unsafe"):
                ledger.query_range(root, "2026-07-28T00:00:00Z", "2026-07-29T00:00:00Z")

    def test_missing_hosted_authority_fails_closed(self) -> None:
        value = promotion_sample()
        raw = (json.dumps(value, sort_keys=True) + "\n").encode()
        ref, digest = exact_ref("promotion-timing-sample", "c")
        record = ledger.build_sample_record(value, raw, ref, digest)
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            RuntimeError, "authority is missing"
        ):
            ledger.bind(Path(temporary) / "not-provisioned", record)

    def test_non_exact_ref_and_wrong_artifact_kind_are_rejected(self) -> None:
        value = promotion_sample()
        raw = (json.dumps(value, sort_keys=True) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "exact GHCR OCI digest ref"):
            ledger.build_sample_record(
                value, raw, "ghcr.io/owner/repository/promotion-timing-sample:latest", "sha256:" + "c" * 64
            )
        ref, digest = exact_ref("ci-timing-summary", "c")
        with self.assertRaisesRegex(ValueError, "artifact kind"):
            ledger.build_sample_record(value, raw, ref, digest)

    def test_renderer_payload_round_trips_as_diagnostic_not_ratchet_authority(self) -> None:
        budget = {
            "budgetSeconds": 300,
            "hardFailSeconds": 1800,
            "timingPolicy": "promotion_timing_ratchet",
            "criticalPath": "promotionReadyAt -> mainReadbackAt",
            "phaseBudgetsSeconds": {},
        }
        payload = renderer.build_payload(
            title="diagnostic",
            gate_key="03.delivery_gate",
            workflow="03. Delivery Gate",
            workflow_run_id="42",
            source_git_sha="a" * 40,
            candidate_digest="sha256:" + "b" * 64,
            gate_budget=budget,
            budget_profile="",
            machine_critical_path_seconds=240,
            critical_path_source="github_run_calendar",
            timestamps={key: "2026-07-28T00:00:00Z" for key in renderer.TIMESTAMP_ARGUMENTS},
            optional_durations={key: 240 for key in renderer.OPTIONAL_DURATION_ARGUMENTS},
            phases=[("promotion", 240)],
            upstream_missing_evidence=[],
            notes=[],
            functional_outcome="pass",
        )
        raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
        ref, digest = exact_ref("ci-timing-summary", "c")
        record = ledger.build_record(payload, raw, ref, digest)
        self.assertEqual(record["recordKind"], "diagnostic_summary")
        self.assertEqual(record["payload"]["outcomePolicy"]["timing"], "DIAGNOSTIC_ONLY")
        self.assertIn("diagnostic only", " ".join(record["payload"]["notes"]))

    def test_remote_authority_embeds_the_same_promotion_sample_validator(self) -> None:
        with mock.patch.object(sync, "_access", return_value=("host", "service", "KEY", "/authority")), \
             mock.patch.object(sync, "_ssh_key") as key_context, \
             mock.patch.object(sync.subprocess, "run") as run:
            key_context.return_value.__enter__.return_value = Path("/tmp/key")
            run.return_value = mock.Mock(
                returncode=0,
                stdout=json.dumps({"authority": ledger.AUTHORITY, "root": "/authority"}),
                stderr="",
            )
            sync._remote_action(action="initialize")
        source = run.call_args.kwargs["input"]
        self.assertIn("<embedded-promotion-timing-ratchet>", source)
        self.assertNotIn(
            "from quwoquan_ops.ci import promotion_timing_ratchet as ratchet", source
        )

    def test_remote_sample_bind_requires_independent_query_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.json"
            raw = write_json(path, promotion_sample())
            ref, digest = exact_ref("promotion-timing-sample", "c")
            expected = ledger.build_sample_record(promotion_sample(), raw, ref, digest)
            with mock.patch.object(sync, "_remote_action", side_effect=[expected, expected]) as remote:
                result = sync.bind_sample_and_readback(path, ref, digest)
        self.assertEqual(result, expected)
        self.assertEqual([call.kwargs["action"] for call in remote.call_args_list], ["bind", "query-sample"])

    def test_remote_sample_bind_rejects_mismatched_query_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.json"
            raw = write_json(path, promotion_sample())
            ref, digest = exact_ref("promotion-timing-sample", "c")
            expected = ledger.build_sample_record(promotion_sample(), raw, ref, digest)
            different = dict(expected)
            different["evidenceDigest"] = "sha256:" + "d" * 64
            with mock.patch.object(sync, "_remote_action", side_effect=[expected, different]), self.assertRaisesRegex(
                RuntimeError, "sample query does not match"
            ):
                sync.bind_sample_and_readback(path, ref, digest)


if __name__ == "__main__":
    unittest.main()
