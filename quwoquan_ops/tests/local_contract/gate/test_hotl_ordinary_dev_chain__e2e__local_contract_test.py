"""Ordinary dirty dev PRE-to-Review-feedback production-chain E2E.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t3
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
CLI_ROOT = ROOT / "quwoquan_ops/cli"
if str(CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(CLI_ROOT))

import handoff_consumer  # noqa: E402
import review_dispatch  # noqa: E402
from lib.agent_governance_contract import contract_schema_version  # noqa: E402
from lib.candidate_evidence import validate_candidate_ref  # noqa: E402
from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402

TARGET = ".agents/skills/dev/SKILL.md"


def _run(
    command: list[str], *, env: dict[str, str], timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    assert completed.returncode == 0, (
        f"command failed ({completed.returncode}): {' '.join(command)}\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    return completed


def _last_line(completed: subprocess.CompletedProcess[str]) -> str:
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    assert lines, f"command emitted no reference: {completed.args}"
    return lines[-1]


def _review_result(
    *, plan: dict[str, Any], evidence_ref: str, evidence: dict[str, Any], role: str,
) -> dict[str, Any]:
    identity = handoff_consumer.named_evidence_identity(evidence_ref, evidence)
    assembled = review_dispatch.build_reviewer_input(
        plan,
        identity,
        evidence_summary={"findings": []},
        reviewer_role=role,
    )
    return {
        "schema_version": contract_schema_version("review_result"),
        "role": role,
        "status": "completed",
        "plan_fingerprint_ref": identity["plan_fingerprint_ref"],
        "plan_fingerprint_digest": identity["plan_fingerprint_digest"],
        "evidence_receipt_ref": identity["receipt_ref"],
        "evidence_receipt_canonical_bytes_sha256": identity["canonical_bytes_sha256"],
        "evidence_run_id": identity["run_id"],
        "evidence_generation_id": identity["generation_id"],
        "execution_fingerprint_ref": identity["execution_fingerprint_ref"],
        "execution_fingerprint_digest": identity["execution_fingerprint_digest"],
        "result_fingerprint_ref": identity["result_fingerprint_ref"],
        "result_fingerprint_digest": identity["result_fingerprint_digest"],
        "assembled_input_byte_count": assembled["assembled_input_byte_count"],
        "assembled_input_digest": assembled["assembled_input_digest"],
        "assembled_input_compression": assembled["compression"],
        "started_at": identity["finished_at"],
        "finished_at": identity["finished_at"],
        "findings": [],
    }


def test_ordinary_dirty_dev_chain_completes_review_but_blocks_scope_admission() -> None:
    case_id = "ordinary-e2e-" + uuid.uuid4().hex
    case = ROOT / ".qwq_output/env/repo/local/hotl-e2e" / case_id
    probe = ROOT / ".agents/skills/dev" / f".{case_id}.txt"
    unrelated = ROOT / ".agents/skills/continue" / f".{case_id}-unrelated.txt"
    evidence_output = ROOT / ".qwq_output/env/repo/runs/review-evidence" / case_id
    candidate_path: Path | None = None
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(case / "cache/bytecode"),
        "QWQ_LOCAL_READINESS_ROOT": str(case / "readiness-state"),
    }
    case.mkdir(parents=True)
    try:
        # PRE is acquired before this test's legal mutation.
        owner_ref = _last_line(
            _run(["make", "feature-context", f"TARGET={TARGET}"], env=env)
        )
        owner_raw = (ROOT / owner_ref).read_bytes()
        owner = json.loads(owner_raw)
        assert owner["target"] == TARGET
        assert owner["resolved_owner"].endswith(
            "agent-skill-review-context-organization/spec.md"
        )

        probe.write_text("ordinary dev mutation\n", encoding="utf-8")
        candidate_ref = _last_line(
            _run(
                [
                    "make",
                    "feature-candidate-evidence",
                    f"OWNER_IDENTITY={owner_ref}",
                    f"CHANGED_PATHS={probe.relative_to(ROOT).as_posix()}",
                ],
                env=env,
            )
        )
        candidate_path = ROOT / candidate_ref
        candidate = json.loads(candidate_path.read_bytes())
        assert candidate["schema_version"] == contract_schema_version(
            "candidate_evidence_manifest"
        )
        assert candidate["owner_identity_ref"] == owner_ref
        assert candidate["changed_paths"] == [probe.relative_to(ROOT).as_posix()]
        assert candidate["impact_plan_identity"]["digest"].startswith("sha256:")
        assert candidate["impact_plan_identity"]["projection_ref"].startswith(
            "local-readiness-plan:sha256:"
        )
        assert candidate["impact_plan_identity"]["timeout_policy_ref"] == (
            "quwoquan_ops/policies/local_readiness_contract.yaml"
        )
        assert candidate["impact_plan_identity"]["timeout_policy_digest"] == (
            candidate["impact_plan"]["timeout_policy"]["digest"]
        )

        # A foreign path may change after POST without contaminating the focused digest.
        unrelated.write_text("foreign concurrent mutation\n", encoding="utf-8")
        _, _, current_candidate, _ = validate_candidate_ref(
            candidate_ref,
            repo_root=ROOT,
            expected_owner_identity_ref=owner_ref,
            expected_changed_paths=[probe.relative_to(ROOT).as_posix()],
        )
        assert unrelated.relative_to(ROOT).as_posix() not in current_candidate[
            "workspace_digests"
        ]

        plan_dir = case / "review"
        _run(
            [
                sys.executable,
                "-B",
                "quwoquan_ops/cli/review_dispatch.py",
                "--workflow",
                "dev",
                "--segment",
                "POST",
                "--changed-paths",
                probe.relative_to(ROOT).as_posix(),
                "--scope",
                TARGET,
                "--owner-identity",
                owner_ref,
                "--candidate-evidence",
                candidate_ref,
                "--out",
                plan_dir.relative_to(ROOT).as_posix(),
            ],
            env=env,
        )
        plan_path = plan_dir / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        assert plan["owner_identity"]["ref"] == owner_ref
        assert plan["candidate_evidence_identity"]["ref"] == candidate_ref
        assert plan["profiles"] == []
        assert [item["role"] for item in plan["reviewers"]] == ["developer"]
        assert [item["id"] for item in plan["evidence"]] == ["review-baseline"]
        assert [item["command"] for item in plan["evidence"]] == [
            "python3 -B quwoquan_ops/gate/verify_review_baseline.py"
        ]
        assert plan["evidence"][0]["timeout_seconds"] == 10
        assert "pytest" not in plan["evidence"][0]["command"]
        assert "make verify-review-dispatch" not in plan["evidence"][0]["command"]

        evidence_ref = _last_line(
            _run(
                [
                    sys.executable,
                    "-B",
                    "quwoquan_ops/cli/evidence_runner.py",
                    "--plan",
                    plan_path.relative_to(ROOT).as_posix(),
                    "--run-id",
                    case_id,
                ],
                env=env,
            )
        )
        evidence_path = ROOT / evidence_ref
        evidence = json.loads(evidence_path.read_bytes())
        assert evidence["terminal"] == {
            "status": "PASS",
            "code": "EVIDENCE.PASSED",
            "failed_evidence": None,
        }
        assert evidence["evidence_class"] == "feedback_only"
        assert evidence["admission_eligible"] is False
        assert len(evidence["evidence"]) == 1
        assert evidence["evidence"][0]["id"] == "review-baseline"
        assert evidence["evidence"][0]["exit_code"] == 0

        result_path = case / "review-result-developer.json"
        result_path.write_bytes(
            canonical_json_bytes(
                _review_result(
                    plan=plan,
                    evidence_ref=evidence_ref,
                    evidence=evidence,
                    role="developer",
                )
            )
        )
        consolidated = _run(
            [
                sys.executable,
                "-B",
                "quwoquan_ops/cli/review_consolidator.py",
                "--plan",
                plan_path.relative_to(ROOT).as_posix(),
                "--evidence",
                evidence_ref,
                "--reviewer-result",
                result_path.relative_to(ROOT).as_posix(),
            ],
            env=env,
        )
        consolidation = json.loads(consolidated.stdout)
        assert consolidation["terminal"] == {"status": "PASS", "codes": []}
        assert consolidation["evidence_identities"][0]["receipt_ref"] == evidence_ref
        assert consolidation["reviewer_result_identities"][0]["result_ref"] == (
            result_path.relative_to(ROOT).as_posix()
        )
        consolidation_path = case / "consolidation.json"
        consolidation_path.write_bytes(canonical_json_bytes(consolidation))

        # Dirty workspace evidence completes Review feedback, but it is never a
        # formal scope-admission grant. The clean temporary-repository success
        # path remains covered by
        # test_scope_and_release_queue_pending_is_contract_advisory.
        readiness_plan = subprocess.run(
            [
                sys.executable,
                "-B",
                "quwoquan_ops/cli/local_readiness.py",
                "plan",
                "--level",
                "scope",
                "--path",
                probe.relative_to(ROOT).as_posix(),
                "--owner-identity",
                owner_ref,
                "--candidate-evidence",
                candidate_ref,
                "--review-consolidation",
                consolidation_path.relative_to(ROOT).as_posix(),
                "--required-evidence",
                evidence_ref,
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        assert readiness_plan.returncode == 2
        assert "REVIEW.EVIDENCE_FEEDBACK_ONLY" in readiness_plan.stderr
        assert not (case / "readiness-state/process/receipts/current").exists()

        # Ordinary development does not depend on an automatic after-edit chain.
        assert "PostToolUse" not in json.loads(
            (ROOT / ".codex/hooks.json").read_text(encoding="utf-8")
        )["hooks"]
        assert "local_readiness_after_edit.py" not in (
            ROOT / ".cursor/hooks.json"
        ).read_text(encoding="utf-8")

        # A verifier/evaluator success is explicitly not an admission grant.
        non_admission = _run(
            [sys.executable, "-B", "quwoquan_ops/gate/verify_governance_pipeline_admission.py"],
            env=env,
            timeout=60,
        )
        assert "EVALUATOR_SELF_CHECK_ONLY_NON_ADMISSION" in non_admission.stdout
        assert "no evidence admission was evaluated" in non_admission.stdout
    finally:
        probe.unlink(missing_ok=True)
        unrelated.unlink(missing_ok=True)
        if candidate_path is not None:
            candidate_path.unlink(missing_ok=True)
        shutil.rmtree(case, ignore_errors=True)
        shutil.rmtree(evidence_output, ignore_errors=True)
