"""Reviewer assembled-input compression contracts.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "quwoquan_ops/cli/review_dispatch.py"


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_review_context_assembler_dispatch", CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


review = _load_cli()


def test_large_candidate_code_health_artifact_compresses_with_auditable_identity() -> None:
    paths = [f"quwoquan_ops/generated/path-{index}.py" for index in range(300)]
    plan = {
        "workflow": "dev", "deliverable": "implementation", "scope": paths[0], "round": 1,
        "contexts": [], "changed_paths": paths,
        "context_bytes": {"limit": 24576},
        "terminal": {"status": "READY", "codes": [], "failed_evidence": []},
        "reviewers": [{
            "role": "developer", "kind": "primary", "required": True,
            "profile": None, "checklist": "roles/developer/checklists/dev/base.md",
        }],
        "fingerprint_receipt": {"ref": "plan-fingerprint.json", "digest": "sha256:" + "4" * 64},
        "owner_identity": {"ref": "owner.json", "canonical_bytes_sha256": "sha256:" + "1" * 64},
        "candidate_evidence_identity": {
            "ref": "candidate.json", "canonical_bytes_sha256": "sha256:" + "2" * 64,
            "changed_paths_digest": "sha256:" + "3" * 64,
        },
    }
    findings = [{
        "code": "CODE_HEALTH.COMPLEXITY_ADVISORY",
        "path": f"quwoquan_ops/generated/path-{index}.py",
        "terminal": "PR_WARN",
        "symbol": f"function_{index}",
        "message": "changed function complexity exceeds advisory " * 4,
        "measure": {"ratio": 1.043},
    } for index in range(50)]
    artifact = {
        "kind": "code-health-report-v1",
        "canonical_bytes_sha256": "sha256:" + "b" * 64,
        "terminal": "PR_WARN",
        "summary": {"changedFiles": 300, "duplicationPercent": 1.043},
        "findings": findings,
    }
    payload = review.build_reviewer_input(
        plan,
        {"receipt_ref": "receipt.json", "canonical_bytes_sha256": "sha256:" + "a" * 64},
        evidence_summary={"terminal": {"status": "PASS"}, "evidence": [{"id": "code-health-delta", "artifact": artifact}]},
        reviewer_role="developer",
    )

    assert payload["assembled_input_byte_count"] <= 24576
    assert payload["compression"]["mode"] != "full"
    projected = payload["assembled_input"]["evidence_summary"]["results"][0]["artifact"]
    assert projected["findings_projection"]["original_count"] == 50
    assert projected["canonical_bytes_sha256"] == "sha256:" + "b" * 64
    assert all("message" not in item and "measure" not in item for item in projected["findings"])
    path_summary = payload["assembled_input"]["changed_paths_and_diff_summary"]
    assert path_summary["paths"] == []
    assert path_summary["paths_projection"]["ref"] == plan["candidate_evidence_identity"]["ref"]
    assert path_summary["paths_projection"]["original_count"] == 300


def test_slightly_over_budget_artifact_falls_back_to_exact_report_ref() -> None:
    paths = [f"quwoquan_ops/generated/path-{index}.py" for index in range(300)]
    plan = {
        "workflow": "dev", "deliverable": "implementation", "scope": paths[0], "round": 1,
        "contexts": [], "changed_paths": paths,
        "context_bytes": {"limit": 24576},
        "terminal": {"status": "READY", "codes": [], "failed_evidence": []},
        "reviewers": [{
            "role": "developer", "kind": "primary", "required": True,
            "profile": None, "checklist": "roles/developer/checklists/dev/base.md",
        }],
        "fingerprint_receipt": {"ref": "plan-fingerprint.json", "digest": "sha256:" + "4" * 64},
        "owner_identity": {"ref": "owner.json", "canonical_bytes_sha256": "sha256:" + "1" * 64},
        "candidate_evidence_identity": {
            "ref": "candidate.json", "canonical_bytes_sha256": "sha256:" + "2" * 64,
            "changed_paths_digest": "sha256:" + "3" * 64,
        },
    }
    findings = [{
        "code": "CODE_HEALTH.COMPLEXITY_ADVISORY",
        "path": f"quwoquan_ops/generated/path-{index}.py",
        "terminal": "PR_WARN", "symbol": f"function_{index}",
        "message": "large", "measure": {"ratio": 1.043},
    } for index in range(200)]
    report_ref = ".qwq_output/env/repo/runs/code-health/exact/report.json"
    report_digest = "sha256:" + "b" * 64
    artifact = {
        "kind": "code-health-report-v1", "ref": report_ref,
        "canonical_bytes_sha256": report_digest, "terminal": "PR_WARN",
        "summary": {"changedFiles": 302, "duplicationPercent": 1.0097},
        "findings": findings,
    }

    payload = review.build_reviewer_input(
        plan,
        {"receipt_ref": "receipt.json", "canonical_bytes_sha256": "sha256:" + "a" * 64},
        evidence_summary={"terminal": {"status": "PASS"}, "evidence": [{"id": "code-health-delta", "artifact": artifact}]},
        reviewer_role="developer",
    )

    assert payload["assembled_input_byte_count"] <= 24576
    projected = payload["assembled_input"]["evidence_summary"]["results"][0]["artifact"]
    assert payload["compression"]["mode"] == "refs_only"
    assert projected["findings"] == []
    assert projected["findings_projection"]["operation"] == "artifact_report_ref"
    assert projected["findings_projection"]["report_ref"] == report_ref
    assert projected["findings_projection"]["report_digest"] == report_digest
    assert projected["findings_projection"]["original_count"] == len(findings)
