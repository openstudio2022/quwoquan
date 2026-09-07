"""Review Code Health exact runner/candidate artifact gate companion.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_ops.gate import verify_review_code_health as review_code_health


def test_review_adapter_requires_runner_exact_range_and_writes_create_once_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = {
        "head_sha": "a" * 40,
        "merge_base_sha": "b" * 40,
        "changed_paths": ["quwoquan_ops/ci/value.py"],
        "candidate_evidence_identity": {
            "changed_paths_digest": "sha256:" + "c" * 64,
            "impact_plan_ref": "local-readiness-plan:sha256:" + "d" * 64,
            "impact_plan_digest": "sha256:" + "d" * 64,
            "ref": ".qwq_output/env/repo/runs/feature-tree/candidates/by-fingerprint/" + "e" * 64 + ".json",
            "canonical_bytes_sha256": "sha256:" + "e" * 64,
        },
    }
    plan_raw = json.dumps(plan, sort_keys=True).encode("utf-8")
    descriptor = tmp_path / "code-health-delta.json"
    report_path = tmp_path / "report.json"
    report = {
        "schema": "quwoquan.code-health-delta", "terminal": "PASS", "candidateSource": "commit",
        "baseSha": plan["merge_base_sha"], "headSha": plan["head_sha"],
        "changedPaths": plan["changed_paths"],
        "changedPathsDigest": plan["candidate_evidence_identity"]["changed_paths_digest"],
        "summary": {"changedFiles": 1}, "findings": [],
        "evidenceFingerprint": {
            "ref": "evidence-fingerprint-v1:sha256:" + "f" * 64,
            "digest": "sha256:" + "f" * 64,
        },
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(review_code_health.RESULT_PATH_ENV, str(descriptor))
    monkeypatch.setenv(review_code_health.SOURCE_HEAD_ENV, plan["head_sha"])
    monkeypatch.setenv(review_code_health.SOURCE_MERGE_BASE_ENV, plan["merge_base_sha"])
    monkeypatch.setattr(review_code_health.verify_review_baseline, "verify", lambda: {"plan_sha256": "sha256:" + hashlib.sha256(plan_raw).hexdigest()})
    monkeypatch.setattr(review_code_health.verify_review_baseline, "_exact_plan_bytes", lambda: (plan_raw, "exact/plan.json"))
    monkeypatch.setattr(review_code_health.verify_review_baseline, "_load_plan", lambda _raw: plan)
    monkeypatch.setattr(review_code_health, "_git", lambda _repo, *args, binary=False: (b"" if binary else plan["head_sha"] if args == ("rev-parse", "HEAD") else plan["merge_base_sha"]))
    monkeypatch.setattr(review_code_health, "verify_delivery", lambda *_args, **_kwargs: (report, report_path, "sha256:" + "1" * 64))
    original_root = review_code_health.ROOT
    monkeypatch.setattr(review_code_health, "ROOT", tmp_path)

    payload, verified_report = review_code_health.verify()
    assert payload["head_sha"] == plan["head_sha"]
    assert payload["base_sha"] == plan["merge_base_sha"]
    assert verified_report == report
    assert json.loads(descriptor.read_text(encoding="utf-8")) == payload
    with pytest.raises(review_code_health.ReviewCodeHealthError, match="create-once"):
        review_code_health.verify()
    monkeypatch.setattr(review_code_health, "ROOT", original_root)


def test_review_adapter_rejects_plan_runner_range_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = tmp_path / "code-health-delta.json"
    plan = {"head_sha": "a" * 40, "merge_base_sha": "b" * 40}
    raw = json.dumps(plan).encode("utf-8")
    monkeypatch.setenv(review_code_health.RESULT_PATH_ENV, str(descriptor))
    monkeypatch.setenv(review_code_health.SOURCE_HEAD_ENV, "c" * 40)
    monkeypatch.setenv(review_code_health.SOURCE_MERGE_BASE_ENV, plan["merge_base_sha"])
    monkeypatch.setattr(review_code_health.verify_review_baseline, "verify", lambda: {})
    monkeypatch.setattr(review_code_health.verify_review_baseline, "_exact_plan_bytes", lambda: (raw, "exact/plan.json"))
    monkeypatch.setattr(review_code_health.verify_review_baseline, "_load_plan", lambda _raw: plan)
    monkeypatch.setattr(review_code_health, "_git", lambda *_args, **_kwargs: plan["head_sha"])
    monkeypatch.setattr(review_code_health, "ROOT", tmp_path)
    with pytest.raises(review_code_health.ReviewCodeHealthError, match="HEAD 漂移"):
        review_code_health.verify()
