from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t1

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from quwoquan_ops.ci.verify_delivery_app_evidence import (
    EvidenceError,
    _evidence_branch,
    verify_app_evidence,
)
from quwoquan_ops.gate.verify_git_branch_policy import load_policy


SHA = "a" * 40
REPOSITORY = "openstudio2022/quwoquan"
WORKFLOW = ".github/workflows/delivery-gate.yml"
APP_JOBS = (
    "Delivery Gate — App Static",
    "Delivery Gate — App Tests Shard 0",
    "Delivery Gate — App Tests Shard 1",
    "Delivery Gate — App Tests Shard 2",
    "Delivery Gate — App Tests Shard 3",
    "Delivery Gate — App Serial",
    "Delivery Gate — App Canonical Coverage",
)


def run_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": 101,
        "repository": {"full_name": REPOSITORY},
        "path": WORKFLOW,
        "event": "push",
        "head_branch": "dev1.0",
        "head_sha": SHA,
        "run_attempt": 2,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-08-26T00:00:00Z",
        "updated_at": "2026-08-26T00:10:00Z",
    }
    payload.update(overrides)
    return payload


def jobs_payload(**overrides: object) -> list[dict[str, object]]:
    jobs: list[dict[str, object]] = []
    for index, name in enumerate(APP_JOBS):
        job: dict[str, object] = {
            "name": name,
            "run_attempt": 2,
            "status": "completed",
            "conclusion": "success",
            "started_at": f"2026-08-26T00:0{index}:00Z",
            "completed_at": f"2026-08-26T00:0{index + 1}:00Z",
        }
        jobs.append(job)
    for key, value in overrides.items():
        setattr_target = int(key.removeprefix("job"))
        jobs[setattr_target].update(value)  # type: ignore[arg-type]
    return jobs


class DeliveryAppEvidenceTest(unittest.TestCase):
    def verify(
        self,
        *,
        runs: list[dict[str, object]] | None = None,
        jobs: list[dict[str, object]] | None = None,
        observed_at: str = "2026-08-26T00:10:01Z",
        deadline_at: str = "2026-08-26T00:25:00Z",
    ) -> dict[str, object]:
        return verify_app_evidence(
            runs=[run_payload()] if runs is None else runs,
            jobs=jobs_payload() if jobs is None else jobs,
            expected_repository=REPOSITORY,
            expected_workflow=WORKFLOW,
            expected_branch="dev1.0",
            expected_sha=SHA,
            observed_at=observed_at,
            deadline_at=deadline_at,
        )

    def test_unique_completed_push_run_and_seven_jobs_are_verified(self) -> None:
        result = self.verify()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["runId"], 101)
        self.assertEqual(result["runAttempt"], 2)
        self.assertEqual(set(result["phaseSeconds"]), {
            "quwoquan_app_static",
            "quwoquan_app_tests",
            "quwoquan_app_serial",
            "quwoquan_app_coverage",
        })
        self.assertEqual(result["phaseSeconds"]["quwoquan_app_tests"], 60)

    def test_zero_or_multiple_run_ids_fail_closed(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "RUN_NOT_FOUND"):
            self.verify(runs=[])
        duplicate = run_payload(id=202)
        with self.assertRaisesRegex(EvidenceError, "RUN_AMBIGUOUS"):
            self.verify(runs=[run_payload(), duplicate])

    def test_run_identity_mismatch_fails_closed(self) -> None:
        cases = (
            {"repository": {"full_name": "other/repository"}},
            {"path": ".github/workflows/other.yml"},
            {"event": "pull_request"},
            {"head_branch": "main"},
            {"head_sha": "b" * 40},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(EvidenceError, "RUN_IDENTITY_MISMATCH"):
                    self.verify(runs=[run_payload(**overrides)])

    def test_only_highest_attempt_is_accepted(self) -> None:
        lower = run_payload(run_attempt=1, conclusion="failure")
        result = self.verify(runs=[lower, run_payload()])
        self.assertEqual(result["runAttempt"], 2)
        mixed = jobs_payload(job0={"run_attempt": 1})
        with self.assertRaisesRegex(EvidenceError, "JOB_ATTEMPT_MISMATCH"):
            self.verify(runs=[lower, run_payload()], jobs=mixed)

    def test_incomplete_run_states_fail_closed(self) -> None:
        for status in ("queued", "in_progress"):
            with self.subTest(status=status):
                with self.assertRaisesRegex(EvidenceError, "RUN_NOT_COMPLETED"):
                    self.verify(runs=[run_payload(status=status, conclusion=None)])

    def test_completed_run_may_have_domain_red_while_app_closure_is_green(self) -> None:
        for conclusion in ("success", "failure", "cancelled", "timed_out"):
            with self.subTest(conclusion=conclusion):
                result = self.verify(runs=[run_payload(conclusion=conclusion)])
                self.assertEqual(result["status"], "verified")

    def test_job_closure_missing_duplicate_extra_or_unsuccessful_fails(self) -> None:
        missing = jobs_payload()[:-1]
        with self.assertRaisesRegex(EvidenceError, "JOB_CLOSURE_MISMATCH"):
            self.verify(jobs=missing)
        duplicate = [*jobs_payload(), copy.deepcopy(jobs_payload()[0])]
        with self.assertRaisesRegex(EvidenceError, "JOB_CLOSURE_MISMATCH"):
            self.verify(jobs=duplicate)
        extra = [*jobs_payload(), {**jobs_payload()[0], "name": "Delivery Gate — App Tests Shard 4"}]
        with self.assertRaisesRegex(EvidenceError, "JOB_CLOSURE_MISMATCH"):
            self.verify(jobs=extra)
        for conclusion in ("failure", "cancelled", "skipped", "timed_out"):
            with self.subTest(conclusion=conclusion):
                failed = jobs_payload(job3={"conclusion": conclusion})
                with self.assertRaisesRegex(EvidenceError, "JOB_NOT_SUCCESSFUL"):
                    self.verify(jobs=failed)
        running = jobs_payload(job3={"status": "in_progress", "conclusion": None})
        with self.assertRaisesRegex(EvidenceError, "JOB_NOT_SUCCESSFUL"):
            self.verify(jobs=running)

    def test_missing_or_reversed_timestamps_fail_instead_of_filling_zero(self) -> None:
        missing = jobs_payload(job0={"completed_at": None})
        with self.assertRaisesRegex(EvidenceError, "JOB_TIMESTAMP_INVALID"):
            self.verify(jobs=missing)
        reversed_time = jobs_payload(
            job0={
                "started_at": "2026-08-26T00:02:00Z",
                "completed_at": "2026-08-26T00:01:00Z",
            }
        )
        with self.assertRaisesRegex(EvidenceError, "JOB_TIMESTAMP_INVALID"):
            self.verify(jobs=reversed_time)

    def test_observation_after_absolute_deadline_is_blocked(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "EVIDENCE_DEADLINE_EXCEEDED"):
            self.verify(
                observed_at="2026-08-26T00:25:01Z",
                deadline_at="2026-08-26T00:25:00Z",
            )

    def test_result_contains_no_token_or_raw_job_payload(self) -> None:
        result = self.verify()
        serialized = repr(result).lower()
        self.assertNotIn("token", serialized)
        self.assertNotIn("authorization", serialized)
        self.assertNotIn("jobs", result)
        datetime.fromisoformat(str(result["observedAt"]).replace("Z", "+00:00")).astimezone(timezone.utc)

    def test_evidence_branch_accepts_integration_and_declared_lanes_only(self) -> None:
        policy = load_policy()
        self.assertEqual(_evidence_branch(policy, ""), "dev1.0")
        self.assertEqual(_evidence_branch(policy, "dev1.0"), "dev1.0")
        self.assertEqual(
            _evidence_branch(policy, "lane/small-fix"), "lane/small-fix"
        )
        for undeclared in ("main", "lane/undeclared", "feature/x"):
            with self.subTest(branch=undeclared):
                with self.assertRaisesRegex(EvidenceError, "INPUT_INVALID"):
                    _evidence_branch(policy, undeclared)

    def test_cli_fixture_emits_exact_workflow_outputs(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_ops"
            / "ci"
            / "verify_delivery_app_evidence.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs_path = root / "runs.json"
            jobs_path = root / "jobs.json"
            output = root / "github-output"
            runs_path.write_text(json.dumps([run_payload()]), encoding="utf-8")
            jobs_path.write_text(json.dumps(jobs_payload()), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--repository",
                    REPOSITORY,
                    "--head-sha",
                    SHA,
                    "--current-run-id",
                    "303",
                    "--run-created-at",
                    # deadline 相对 run 创建时刻，用当前时刻避免 fixture 过期炸弹。
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "--evidence-deadline-seconds",
                    "86400",
                    "--runs-json",
                    str(runs_path),
                    "--jobs-json",
                    str(jobs_path),
                    "--github-output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            values = dict(
                line.split("=", 1)
                for line in output.read_text(encoding="utf-8").splitlines()
            )
            payload = json.loads(completed.stdout)
        self.assertEqual(values["run_id"], "101")
        self.assertEqual(values["run_attempt"], "2")
        self.assertEqual(values["phase_quwoquan_app_tests"], "60")
        self.assertRegex(values["job_closure_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            payload["authority"],
            {
                "lastHttpStatus": None,
                "matchedRunCount": 1,
                "rateLimitRemaining": None,
                "rateLimitResetEpoch": None,
                "requestCount": 0,
                "retryCount": 0,
            },
        )
        self.assertNotIn("token", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
