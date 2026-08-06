"""Independent post review must bind a real SDK run into canonical evidence."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.controller import post_independent_review
from content.review.independent import apply_independent_post_review
from core.control_types import AgentProvider
from core.data_issue import DataIssueCode, DataRecoveryAction

EXECUTION_ID = "20260722--travel-article-supply--test-region-a--pilot-903"
OBJECT_REF = "test-entity-a__article_source_a"


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_agent_provider_value_accepts_only_governed_provider_values() -> None:
    assert post_independent_review._agent_provider_value(AgentProvider.CODEX_SDK) == "codex_sdk"
    assert post_independent_review._agent_provider_value("cursor_sdk") == "cursor_sdk"
    with pytest.raises(ValueError, match="unregistered_sdk"):
        post_independent_review._agent_provider_value("unregistered_sdk")


def test_independent_post_review_replaces_deterministic_reviewer_binding(
    tmp_path: Path,
) -> None:
    review_dir = tmp_path / "5.review"
    _write(review_dir / "review.json", {"decision": "approved", "issues": []})
    _write(
        review_dir / "attestation.json",
        {
            "schema": "quwoquan_data.review_attestation",
            "stage": "5.review",
            "executionId": EXECUTION_ID,
            "executionBinding": "frozen",
            "objectRef": OBJECT_REF,
            "decision": "approved",
            "deterministicGate": {"status": "passed", "issues": []},
            "independentReviewer": {
                "status": "passed",
                "provider": "review_controller",
                "model": "deterministic",
                "modelFamily": "deterministic",
                "runId": "deterministic-review",
                "resultHash": "sha256:" + "a" * 64,
            },
            "mediaRefReview": {"status": "passed", "issues": []},
            "repair": {"status": "not_required"},
            "finalizationRef": "5.review/finalization_report.json",
            "evidenceIndexRef": "5.review/evidence_index.json",
        },
    )
    _write(
        review_dir / "evidence_index.json",
        {
            "schema": "quwoquan_data.evidence_index",
            "stage": "5.review",
            "executionId": EXECUTION_ID,
            "executionBinding": "frozen",
            "objectRef": OBJECT_REF,
            "evidence": [
                {
                    "kind": "runtime_review",
                    "ref": "5.review/reviewer_result.json",
                    "sha256": "sha256:" + "b" * 64,
                }
            ],
        },
    )
    response = {
        "schema": "quwoquan_data.post_reviewer_response",
        "executionId": EXECUTION_ID,
        "objectRef": OBJECT_REF,
        "decision": "approved",
        "issues": [],
        "findings": ["正文、来源、实体和媒体绑定均已独立复核。"],
    }

    issues = apply_independent_post_review(
        review_dir=review_dir,
        provider="cursor_sdk",
        model="grok-4.5",
        model_family="grok",
        run_id="review-run-903",
        result_payload=response,
    )

    assert issues == []
    result = json.loads((review_dir / "reviewer_result.json").read_text(encoding="utf-8"))
    attestation = json.loads((review_dir / "attestation.json").read_text(encoding="utf-8"))
    evidence = json.loads((review_dir / "evidence_index.json").read_text(encoding="utf-8"))
    assert result["provider"] == "cursor_sdk"
    assert result["modelFamily"] == "grok"
    assert result["runId"] == "review-run-903"
    assert attestation["independentReviewer"]["runId"] == "review-run-903"
    reviewer_rows = [
        row
        for row in evidence["evidence"]
        if row["ref"] == "5.review/reviewer_result.json"
    ]
    assert len(reviewer_rows) == 1
    assert reviewer_rows[0]["kind"] == "independent_reviewer_result"


def test_independent_post_review_returns_typed_object_issue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    object_dir = tmp_path / "object"
    _write(object_dir / "manifest.json", {"vertical": "travel", "assets": []})
    author_family = SimpleNamespace(value="grok")
    reviewer_family = SimpleNamespace(value="composer")
    pair = SimpleNamespace(
        author=SimpleNamespace(model_id="grok-4.5", family=author_family),
        reviewer=SimpleNamespace(
            model_id="composer-2.5",
            family=reviewer_family,
            parameters=(),
        ),
    )
    response = {
        "schema": "quwoquan_data.post_reviewer_response",
        "executionId": EXECUTION_ID,
        "objectRef": OBJECT_REF,
        "decision": "revision_needed",
        "issues": ["image caption does not match its paragraph"],
        "findings": ["media placement was reviewed"],
    }
    outcome = SimpleNamespace(
        succeeded=True,
        provider=AgentProvider.CURSOR_SDK,
        result_text=json.dumps(response),
        status=SimpleNamespace(value="finished"),
        run_id="review-run-904",
        agent_id="review-agent-904",
        request_id="review-request-904",
        duration_ms=100,
        error_code="",
        message="",
    )
    monkeypatch.setattr(
        "content.execution.model_contract.execution_model_pair_for_execution",
        lambda _execution_id: pair,
    )
    monkeypatch.setattr(
        "content.execution.agent.agent_worker._default_managed_agent_runner_isolated",
        lambda _ctx, _prompt: outcome,
    )
    monkeypatch.setattr(
        post_independent_review.content_object,
        "content_object_dir",
        lambda _execution_id, _ref: object_dir,
    )
    monkeypatch.setattr(
        post_independent_review,
        "_existing_independent_review_issues",
        lambda *_args, **_kwargs: ["review required"],
    )
    monkeypatch.setattr(post_independent_review, "_media_policy", lambda *_args: "{}")
    monkeypatch.setattr(post_independent_review, "render_prompt", lambda *_args, **_kwargs: "prompt")
    monkeypatch.setattr(
        post_independent_review,
        "ExecutionContext",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        post_independent_review,
        "apply_independent_post_review",
        lambda **_kwargs: ["image caption does not match its paragraph"],
    )
    ctx = SimpleNamespace(
        execution_id=EXECUTION_ID,
        entity_ids=["test-entity-a"],
        spec=SimpleNamespace(to_dict=dict),
        managed=True,
        runtime="local",
        agent_provider="cursor_sdk",
        release_only=False,
    )

    issues = post_independent_review.run_post_independent_reviews(ctx, [OBJECT_REF])

    assert len(issues) == 1
    assert issues[0].code is DataIssueCode.QUALITY_FAILED
    assert issues[0].ref == OBJECT_REF
    assert issues[0].recovery is DataRecoveryAction.REWIND_COMPOSE
