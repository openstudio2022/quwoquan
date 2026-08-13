# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-002
from __future__ import annotations

import copy
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.cli.prod import resolve_prod_release_state as resolver
from quwoquan_ops.tests.support.rollout_stage_promotion_evidence_test_support import (
    promotion_evidence,
)


def digest(character: str) -> str:
    return "sha256:" + character * 64


class ResolveProdReleaseStateContractTest(unittest.TestCase):
    stable = digest("a")
    target = digest("b")
    next_target = digest("c")

    def _readback(
        self,
        *,
        stage: str = "canary",
        decision: str = "continue",
        from_candidate: str | None = None,
        to_candidate: str | None = None,
        last_good: str | None = None,
    ) -> dict:
        source = from_candidate or self.stable
        target = to_candidate or self.target
        if last_good is None:
            last_good = (
                target
                if stage == "100" and decision in {"continue", "rolled_back"}
                else source
            )
        request = {
            "schema": hosted_release_ledger.REQUEST_SCHEMA,
            "service": resolver.SERVICE,
            "fromCandidateDigest": source,
            "toCandidateDigest": target,
            "step": {"canary": "0", "5": "5", "20": "20", "50": "50", "100": "100"}[stage],
            "stage": stage,
            "triggerStage": stage,
            "fromReleaseEvidenceRef": f"ghcr.io/example/quwoquan/release-evidence@{source}",
            "toReleaseEvidenceRef": f"ghcr.io/example/quwoquan/release-evidence@{target}",
            "fromImageTransportTag": "source-transport",
            "toImageTransportTag": "target-transport",
            "decision": decision,
            "rollbackOutcome": (
                decision
                if decision in {"rolled_back", "rollback_failed"}
                else "not_triggered"
            ),
            "rollbackEvidence": (
                {
                    "triggered": True,
                    "startedAt": "2026-07-28T00:04:00Z",
                    "endedAt": "2026-07-28T00:04:01Z",
                    "durationMs": 1000,
                    "postChecks": [
                        {
                            "name": "rollback-health",
                            "status": (
                                "passed" if decision == "rolled_back" else "failed"
                            ),
                            "receiptDigest": digest("4"),
                        }
                    ],
                }
                if decision in {"rolled_back", "rollback_failed"}
                else {"triggered": False}
            ),
            "artifactDigest": digest("d"),
            "imageDigest": digest("e"),
            "configDigest": digest("f"),
            "contractGraphDigest": digest("1"),
            "adapterDigest": digest("2"),
            "expectedGeneration": 0,
            "sloReadback": {
                "sampleCount": 100,
                **(
                    {
                        "promotionEvidence": promotion_evidence(
                            candidate_id=target,
                            artifact_digest=digest("d"),
                            stage=stage,
                        )
                    }
                    if decision == "continue"
                    else {}
                ),
            },
            "postChecks": [
                {
                    "name": "hosted-health",
                    "status": "passed",
                    "receiptDigest": digest("3"),
                }
            ],
            "lastGoodCandidateDigest": last_good,
            "verifiedAt": "2026-07-28T00:05:00Z",
        }
        with tempfile.TemporaryDirectory() as temporary:
            return hosted_release_ledger.commit(Path(temporary), request)

    def test_fetch_uses_only_the_hosted_release_ledger_authority(self) -> None:
        payload = {
            "schema": "prod-hosted-release-readback",
            "authority": "prod-hosted-service-plane",
            "state": {},
            "receipt": {},
            "receiptRef": "",
        }

        def write_readback(
            argv: list[str],
            **_: object,
        ) -> subprocess.CompletedProcess[str]:
            output = Path(argv[argv.index("--output-path") + 1])
            output.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with mock.patch.object(
            resolver.subprocess,
            "run",
            side_effect=write_readback,
        ) as mocked_run:
            resolved = resolver._fetch_hosted_readback()

        self.assertEqual(resolved, payload)
        command = mocked_run.call_args.args[0]
        self.assertEqual(
            command[0:2],
            ["bash", "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh"],
        )
        self.assertEqual(
            command[command.index("--operation") + 1],
            "release-ledger-fetch",
        )
        self.assertEqual(command[command.index("--service") + 1], "prod-stack")
        self.assertNotIn("ssh", command)

    def test_fetch_failure_is_gate_block(self) -> None:
        completed = subprocess.CompletedProcess(
            ["bash"],
            2,
            "",
            "authority unavailable",
        )
        with mock.patch.object(resolver.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(resolver.GateBlockError, "fetch failed"):
                resolver._fetch_hosted_readback()

    def test_same_target_preserves_original_source_and_advances_stage(self) -> None:
        expectations = {
            "canary": "5",
            "5": "20",
            "20": "50",
            "50": "100",
            "100": "complete",
        }
        for stage, expected_resume in expectations.items():
            with self.subTest(stage=stage):
                resolved = resolver.resolve_release_state(
                    self._readback(stage=stage),
                    to_candidate_digest=self.target,
                )
                self.assertEqual(
                    resolved,
                    {
                        "fromCandidateDigest": self.stable,
                        "resumeStage": expected_resume,
                        "authority": hosted_release_ledger.AUTHORITY,
                    },
                )

    def test_pause_resumes_the_current_stage(self) -> None:
        for stage in ("canary", "5", "20", "50", "100"):
            with self.subTest(stage=stage):
                resolved = resolver.resolve_release_state(
                    self._readback(stage=stage, decision="pause"),
                    to_candidate_digest=self.target,
                )
                self.assertEqual(resolved["fromCandidateDigest"], self.stable)
                self.assertEqual(resolved["resumeStage"], stage)

    def test_different_target_starts_from_a_full_stable_candidate(self) -> None:
        resolved = resolver.resolve_release_state(
            self._readback(stage="100"),
            to_candidate_digest=self.next_target,
        )
        self.assertEqual(
            resolved,
            {
                "fromCandidateDigest": self.target,
                "resumeStage": "canary",
                "authority": hosted_release_ledger.AUTHORITY,
            },
        )

    def test_different_target_starts_from_a_successful_rollback(self) -> None:
        readback = self._readback(
            stage="100",
            decision="rolled_back",
            from_candidate=self.target,
            to_candidate=self.stable,
            last_good=self.stable,
        )
        resolved = resolver.resolve_release_state(
            readback,
            to_candidate_digest=self.next_target,
        )
        self.assertEqual(resolved["fromCandidateDigest"], self.stable)
        self.assertEqual(resolved["resumeStage"], "canary")

    def test_same_rolled_back_target_restarts_as_candidate_bound_noop(self) -> None:
        readback = self._readback(
            stage="100",
            decision="rolled_back",
            from_candidate=self.target,
            to_candidate=self.stable,
            last_good=self.stable,
        )
        resolved = resolver.resolve_release_state(
            readback,
            to_candidate_digest=self.stable,
        )
        self.assertEqual(
            resolved,
            {
                "fromCandidateDigest": self.stable,
                "resumeStage": "canary",
                "authority": hosted_release_ledger.AUTHORITY,
            },
        )

    def test_failed_candidate_after_rollback_is_sealed_without_redeployment(self) -> None:
        readback = self._readback(
            stage="100",
            decision="rolled_back",
            from_candidate=self.target,
            to_candidate=self.stable,
            last_good=self.stable,
        )
        resolved = resolver.resolve_release_state(
            readback,
            to_candidate_digest=self.target,
        )
        self.assertEqual(
            resolved,
            {
                "fromCandidateDigest": self.stable,
                "resumeStage": "complete",
                "authority": hosted_release_ledger.AUTHORITY,
            },
        )

    def test_main_can_write_the_validated_hosted_readback_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "validated/readback.json"
            readback = self._readback()
            with (
                mock.patch.object(
                    resolver,
                    "_fetch_hosted_readback",
                    return_value=readback,
                ),
                mock.patch(
                    "sys.argv",
                    [
                        str(resolver.__file__),
                        "--to-candidate-digest",
                        self.target,
                        "--readback-output",
                        str(output),
                    ],
                ),
                redirect_stdout(io.StringIO()),
                redirect_stderr(io.StringIO()),
            ):
                exit_code = resolver.main()
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), readback)

    def test_partial_or_paused_ledger_blocks_a_different_target(self) -> None:
        for readback in (
            self._readback(stage="50"),
            self._readback(stage="100", decision="pause"),
        ):
            with self.assertRaisesRegex(
                resolver.GateBlockError,
                "different target requires",
            ):
                resolver.resolve_release_state(
                    readback,
                    to_candidate_digest=self.next_target,
                )

    def test_rollback_failed_candidate_can_only_seal_terminal_evidence(self) -> None:
        readback = self._readback(
            stage="100",
            decision="rollback_failed",
            last_good=self.stable,
        )
        resolved = resolver.resolve_release_state(
            readback,
            to_candidate_digest=self.target,
        )
        self.assertEqual(resolved["fromCandidateDigest"], self.stable)
        self.assertEqual(resolved["resumeStage"], "complete")
        with self.assertRaisesRegex(resolver.GateBlockError, "rollback_failed"):
            resolver.resolve_release_state(
                readback,
                to_candidate_digest=self.next_target,
            )

    def test_empty_historical_and_incomplete_readbacks_are_rejected(self) -> None:
        empty = {
            "schema": hosted_release_ledger.READBACK_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "state": {},
            "receipt": {},
            "receiptRef": "",
        }
        historical = {
            "schema": "legacy-release-record",
            "authority": hosted_release_ledger.AUTHORITY,
            "state": {},
            "receipt": {},
            "receiptRef": "",
        }
        incomplete = copy.deepcopy(self._readback())
        incomplete["receipt"].pop("toCandidateDigest")
        for value in (empty, historical, incomplete):
            with self.assertRaises(resolver.GateBlockError):
                resolver.resolve_release_state(
                    value,
                    to_candidate_digest=self.target,
                )

    def test_receipt_tampering_is_rejected(self) -> None:
        readback = copy.deepcopy(self._readback())
        readback["receipt"]["imageDigest"] = digest("9")
        with self.assertRaisesRegex(resolver.GateBlockError, "not receipt-bound"):
            resolver.resolve_release_state(
                readback,
                to_candidate_digest=self.target,
            )

    def test_fixed_stage_receipt_history_is_required_and_strict(self) -> None:
        for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values():
            readback = copy.deepcopy(self._readback())
            readback["state"].pop(field)
            with self.subTest(missing=field), self.assertRaisesRegex(
                resolver.GateBlockError,
                "state has a non-canonical shape",
            ):
                resolver.resolve_release_state(
                    readback,
                    to_candidate_digest=self.target,
                )

        malformed = copy.deepcopy(self._readback())
        malformed["state"]["percent_50_receipt_id"] = "not-a-receipt"
        with self.assertRaisesRegex(
            resolver.GateBlockError,
            "not a canonical receipt id",
        ):
            resolver.resolve_release_state(
                malformed,
                to_candidate_digest=self.target,
            )

        wrong_stage = copy.deepcopy(self._readback())
        wrong_stage["state"]["canary_receipt_id"] = ""
        wrong_stage["state"]["percent_50_receipt_id"] = wrong_stage["state"][
            "receipt_id"
        ]
        with self.assertRaisesRegex(
            resolver.GateBlockError,
            "not bound to trigger stage",
        ):
            resolver.resolve_release_state(
                wrong_stage,
                to_candidate_digest=self.target,
            )

    def test_main_outputs_only_canonical_resolution_fields(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(
                resolver,
                "_fetch_hosted_readback",
                return_value=self._readback(),
            ),
            mock.patch(
                "sys.argv",
                [
                    str(resolver.__file__),
                    "--to-candidate-digest",
                    self.target,
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = resolver.main()
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            set(payload),
            {"fromCandidateDigest", "resumeStage", "authority"},
        )

    def test_main_gate_block_is_nonzero(self) -> None:
        empty = {
            "schema": hosted_release_ledger.READBACK_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "state": {},
            "receipt": {},
            "receiptRef": "",
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(resolver, "_fetch_hosted_readback", return_value=empty),
            mock.patch(
                "sys.argv",
                [
                    str(resolver.__file__),
                    "--to-candidate-digest",
                    self.target,
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = resolver.main()
        self.assertNotEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("GATE_BLOCK", stderr.getvalue())

    def test_shell_output_remains_the_three_candidate_only_values(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(
                resolver,
                "_fetch_hosted_readback",
                return_value=self._readback(),
            ),
            mock.patch(
                "sys.argv",
                [
                    str(resolver.__file__),
                    "--to-candidate-digest",
                    self.target,
                    "--output-format",
                    "shell",
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = resolver.main()
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            stdout.getvalue().splitlines(),
            [
                f"RESOLVED_FROM_CANDIDATE_DIGEST={self.stable}",
                "RESOLVED_RESUME_STAGE=5",
                (
                    "RESOLVED_HOSTED_AUTHORITY="
                    + hosted_release_ledger.AUTHORITY
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
