"""Triggered handoff exact-byte production-chain E2E.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-001a
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
CLI_ROOT = ROOT / "quwoquan_ops/cli"
if str(CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(CLI_ROOT))

import evidence_runner  # noqa: E402
import handoff_consumer  # noqa: E402
import review_dispatch  # noqa: E402
from lib import handoff_store  # noqa: E402
from lib.agent_governance_contract import contract_schema_version  # noqa: E402
from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402
from lib.governance_pipeline_admission import (  # noqa: E402
    current_repository_input,
    load_contract,
)
from lib.governance_pipeline_admission import adapters  # noqa: E402

TARGET = (
    "specs/feature-tree/runtime/development-workflow-governance/"
    "governance-pipeline-observe-only/spec.md"
)
CHANGED = "quwoquan_ops/cli/lib/governance_pipeline_admission/.hotl-e2e-probe.txt"


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


def _refs() -> dict[str, Any]:
    return {
        "owner_manifest": None,
        "local_scope_ready": None,
        "local_release_ready": None,
        "review_plan": None,
        "named_evidence": {},
        "review_consolidation": None,
        "handoff": None,
        "human_calibration": None,
        "objective_inspect": None,
        "hotl_inspect": None,
        "hosted_authority_source": None,
        "external": {},
    }


def test_triggered_handoff_rejects_dirty_workspace_feedback_only_evidence() -> None:
    case_id = "handoff-e2e-" + uuid.uuid4().hex
    case = ROOT / ".qwq_output/env/repo/local/hotl-e2e" / case_id
    probe = ROOT / CHANGED
    evidence_output = ROOT / ".qwq_output/env/repo/runs/review-evidence" / case_id
    handoff_output = ROOT / ".qwq_output/env/repo/runs/handoff" / case_id
    candidate_path: Path | None = None
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(case / "cache/bytecode"),
    }
    case.mkdir(parents=True)
    try:
        owner_ref = _last_line(
            _run(["make", "feature-context", f"TARGET={TARGET}"], env=env)
        )
        probe.write_text("triggered handoff mutation\n", encoding="utf-8")
        candidate_ref = _last_line(
            _run(
                [
                    "make",
                    "feature-candidate-evidence",
                    f"OWNER_IDENTITY={owner_ref}",
                    f"CHANGED_PATHS={CHANGED}",
                ],
                env=env,
            )
        )
        candidate_path = ROOT / candidate_ref
        plan_dir = case / "review"
        _run(
            [
                sys.executable, "-B", "quwoquan_ops/cli/review_dispatch.py",
                "--workflow", "dev", "--segment", "POST",
                "--changed-paths", CHANGED, "--scope", TARGET,
                "--owner-identity", owner_ref,
                "--candidate-evidence", candidate_ref,
                "--out", plan_dir.relative_to(ROOT).as_posix(),
            ],
            env=env,
        )
        plan_path = plan_dir / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        evidence_run = subprocess.run(
            [
                sys.executable, "-B", "quwoquan_ops/cli/evidence_runner.py",
                "--source-mode", "workspace",
                "--plan", plan_path.relative_to(ROOT).as_posix(),
                "--run-id", case_id,
            ],
            cwd=ROOT, env=env, text=True, capture_output=True,
            check=False, timeout=900,
        )
        assert evidence_run.returncode in (0, 1), evidence_run.stderr
        evidence_ref = _last_line(evidence_run)
        evidence_path = ROOT / evidence_ref
        evidence = json.loads(evidence_path.read_bytes())
        assert evidence["evidence_class"] == "feedback_only"
        assert evidence["admission_eligible"] is False
        if evidence["terminal"]["status"] == "GATE_BLOCK":
            assert any(
                item["exit_code"] != 0 and item["required"]
                for item in evidence["evidence"]
            )
            return
        assert evidence["terminal"]["status"] == "PASS"

        result_paths: list[Path] = []
        for role in ("developer", "ops"):
            result_path = case / f"review-result-{role}.json"
            result_path.write_bytes(
                canonical_json_bytes(
                    _review_result(
                        plan=plan, evidence_ref=evidence_ref,
                        evidence=evidence, role=role,
                    )
                )
            )
            result_paths.append(result_path)
        command = [
            sys.executable, "-B", "quwoquan_ops/cli/review_consolidator.py",
            "--plan", plan_path.relative_to(ROOT).as_posix(),
            "--evidence", evidence_ref,
        ]
        for result_path in result_paths:
            command.extend(
                ["--reviewer-result", result_path.relative_to(ROOT).as_posix()]
            )
        consolidation = json.loads(_run(command, env=env).stdout)
        assert consolidation["terminal"] == {"status": "PASS", "codes": []}
        assert consolidation["evidence_identities"][0]["evidence_class"] == "feedback_only"
        consolidation_path = case / "consolidation.json"
        consolidation_path.write_bytes(canonical_json_bytes(consolidation))

        handoff_input = {
            "run_id": case_id,
            "intent": "must reject mutable feedback evidence",
            "triggers": ["evidence_reuse"],
            "artifacts": [CHANGED],
            "pending_dispositions": [],
            "downstream": "plan-next",
            "owner_identity_ref": owner_ref,
            "candidate_evidence_ref": candidate_ref,
            "review_plan_ref": plan_path.relative_to(ROOT).as_posix(),
            "evidence_receipt_refs": [evidence_ref],
            "reviewer_result_refs": [
                item.relative_to(ROOT).as_posix() for item in result_paths
            ],
            "review_consolidation_ref": consolidation_path.relative_to(ROOT).as_posix(),
            "recovery_token": "rerun_evidence_for_new_fingerprint",
        }
        input_path = case / "handoff-input.json"
        input_path.write_bytes(canonical_json_bytes(handoff_input))
        attempted = subprocess.run(
            [
                sys.executable, "-B", "quwoquan_ops/cli/handoff_manifest.py",
                "--input", input_path.relative_to(ROOT).as_posix(),
            ],
            cwd=ROOT, env=env, text=True, capture_output=True,
            check=False, timeout=60,
        )
        assert attempted.returncode == 2
        assert "REVIEW.EVIDENCE_FEEDBACK_ONLY" in attempted.stderr
        assert not handoff_output.exists()
    finally:
        probe.unlink(missing_ok=True)
        if candidate_path is not None:
            candidate_path.unlink(missing_ok=True)
        shutil.rmtree(case, ignore_errors=True)
        shutil.rmtree(evidence_output, ignore_errors=True)
        shutil.rmtree(handoff_output, ignore_errors=True)
