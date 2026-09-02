from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from core.control_types import AgentProvider
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.controller.execute import review_image_supported_api_input as review_command
from content.source.professional_image_supported_api_contract import load_reviewer_results
from content.execution.model_contract import governed_cursor_grok_model
from content.source.source_review_journal import (
    SourceReviewReplayError,
    run_source_review,
)


def test_source_review_invokes_once_and_replays_create_once_attempt(tmp_path) -> None:
    identity = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "executionBundleDigest": "sha256:" + "4" * 64,
        "handoffDigest": "sha256:" + "5" * 64,
        "requestDigest": "sha256:" + "6" * 64,
    }
    calls: list[str] = []

    def runner(prompt: str) -> AgentRunOutcome:
        calls.append(prompt)
        return AgentRunOutcome.finished(
            provider=AgentProvider.CURSOR_SDK, run_id="grok-run", result_text="{}",
        )

    result, attempt = run_source_review(
        source_evidence_root=tmp_path / "evidence", source_review=identity,
        model=governed_cursor_grok_model(), prompt="review exact bytes", runner=runner,
    )
    assert calls == ["review exact bytes"]
    assert attempt.is_file()
    assert result["attempt"]["provider"] == "cursor_sdk"
    assert result["attempt"]["status"] == "finished"
    assert "capacityReceipt" not in result
    replay, replay_attempt = run_source_review(
        source_evidence_root=tmp_path / "evidence", source_review=identity,
        model=governed_cursor_grok_model(), prompt="review exact bytes", runner=runner,
    )
    assert calls == ["review exact bytes"]
    assert replay_attempt == attempt
    assert replay["attempt"]["attemptDigest"] == result["attempt"]["attemptDigest"]
    # 重放必须能重建下游消费的完整 journal，而不是缺键后在消费者处 KeyError。
    assert replay["outcome"].succeeded
    assert replay["outcome"].result_text == "{}"
    assert replay["outcome"].run_id == "grok-run"


def test_source_review_records_real_failure_then_retries_only_that_task(tmp_path) -> None:
    identity = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "executionBundleDigest": "sha256:" + "4" * 64,
        "handoffDigest": "sha256:" + "5" * 64,
        "requestDigest": "sha256:" + "6" * 64,
    }
    calls = 0

    def runner(_prompt: str) -> AgentRunOutcome:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("provider-specific failure")
        return AgentRunOutcome.finished(
            provider=AgentProvider.CURSOR_SDK,
            run_id="grok-run-2",
            result_text="{}",
        )

    failed, first_path = run_source_review(
        source_evidence_root=tmp_path / "evidence",
        source_review=identity,
        model=governed_cursor_grok_model(),
        prompt="review exact bytes",
        runner=runner,
    )
    assert failed["attempt"]["status"] == "error"
    assert failed["attempt"]["errorCode"] == "semantic_source_review_invocation_exception"
    assert "provider-specific failure" not in first_path.read_text(encoding="utf-8")

    succeeded, second_path = run_source_review(
        source_evidence_root=tmp_path / "evidence",
        source_review=identity,
        model=governed_cursor_grok_model(),
        prompt="review exact bytes",
        runner=runner,
    )
    assert calls == 2
    assert succeeded["attempt"]["status"] == "finished"
    assert succeeded["attempt"]["attempt"] == 2
    assert second_path.name == "002.json"


def test_image_source_runner_uses_governed_typed_selection_in_isolated_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    expected = AgentRunOutcome.finished(
        provider=AgentProvider.CURSOR_SDK,
        run_id="isolated-review",
        result_text="{}",
    )

    def isolated(**kwargs: object) -> AgentRunOutcome:
        calls.append(dict(kwargs))
        return expected

    monkeypatch.setattr(
        "content.execution.agent.agent_worker.run_source_review_agent_isolated",
        isolated,
    )

    assert review_command._source_runner("review exact bytes") is expected
    binding = review_command.active_runtime_policy().explicit_semantic_selection(
        "cursor_grok"
    )
    assert calls == [
        {
            "runtime": binding.runtime,
            "model_selection": binding.binding.selection,
            "prompt": "review exact bytes",
        }
    ]


def test_replay_of_finished_attempt_without_result_is_typed(
    tmp_path,
) -> None:
    """缺少结果的 attempt 必须是 typed failure，而不是下游 KeyError。"""
    identity = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "executionBundleDigest": "sha256:" + "4" * 64,
        "handoffDigest": "sha256:" + "5" * 64,
        "requestDigest": "sha256:" + "6" * 64,
    }
    calls: list[str] = []

    def runner(prompt: str) -> AgentRunOutcome:
        calls.append(prompt)
        return AgentRunOutcome.finished(
            provider=AgentProvider.CURSOR_SDK, run_id="grok-run", result_text="{}",
        )

    _result, attempt_path = run_source_review(
        source_evidence_root=tmp_path / "evidence", source_review=identity,
        model=governed_cursor_grok_model(), prompt="review exact bytes", runner=runner,
    )
    payload = json.loads(attempt_path.read_text(encoding="utf-8"))
    payload.pop("resultText")
    attempt_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SourceReviewReplayError) as captured:
        run_source_review(
            source_evidence_root=tmp_path / "evidence", source_review=identity,
            model=governed_cursor_grok_model(), prompt="review exact bytes", runner=runner,
        )

    assert captured.value.code == "DATA.AGENT.REVIEW_RESULT_UNAVAILABLE"
    assert calls == ["review exact bytes"]


def test_host_review_result_binds_handoff_asset_and_replays_create_once(
    tmp_path: Path,
) -> None:
    """现役 loader 只消费 host review result，并对 identity/asset 漂移 fail closed。"""
    from content.source.host_source_review import (
        HostSourceReviewError,
        prepare_host_source_review_request,
        record_host_source_review_result,
    )

    root = tmp_path / "output"
    asset = root / "candidates/candidate/original/asset.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"immutable-image")
    content_sha = "sha256:" + hashlib.sha256(b"immutable-image").hexdigest()
    evidence_refs: dict[str, str] = {}
    for role in ("acquisition", "media_probe", "safety_scan", "rights_attribution"):
        path = root / f"candidates/candidate/{role}.json"
        path.write_text(
            json.dumps({"role": role, "assetId": "candidate"}), encoding="utf-8"
        )
        evidence_refs[role] = f"candidates/candidate/{role}.json"
    identity = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64,
        "entityCatalogDigest": "sha256:" + "3" * 64,
        "executionBundleDigest": "sha256:" + "4" * 64,
        "handoffDigest": "sha256:" + "5" * 64,
    }
    request, request_ref = prepare_host_source_review_request(
        evidence_root=root, source_identity=identity, asset_kind="image",
        asset_id="candidate",
        asset_ref="candidates/candidate/original/asset.png",
        content_sha256=content_sha, entity_id="西湖", observed_entity_id="西湖",
        content_ref="https://example.com/candidate",
        evidence_refs=evidence_refs,
    )
    result_input = {
        "schema": "quwoquan_data.host_source_review_result_input",
        "requestRef": request_ref,
        "requestDigest": request["requestDigest"],
        "actor": {
            "host": "cursor",
            "sessionId": "journal-session",
            "modelFamily": "gpt-5",
            "auditRunId": "journal-audit-001",
        },
        "reviewedAt": "2026-08-13T09:00:00Z",
        "verdict": {
            "status": "passed", "entityMatch": "matched",
            "qualityStatus": "passed", "privacyRisk": "none",
            "minorRisk": "none", "maliciousMediaRisk": "none",
            "watermarkStatus": "absent", "findings": [],
        },
    }
    first, result_ref = record_host_source_review_result(
        evidence_root=root, result_input=result_input
    )
    replay, replay_ref = record_host_source_review_result(
        evidence_root=root, result_input=result_input
    )
    assert replay_ref == result_ref
    assert replay["resultDigest"] == first["resultDigest"]
    loaded = load_reviewer_results(
        (result_ref,), root=root, catalog={},
        digest=lambda value: "", source_review_identity=identity,
    )
    assert loaded["candidate"]["sourceIdentity"] == identity
    superseding_identity = {
        **identity,
        "sourceDigest": "sha256:" + "9" * 64,
        "handoffDigest": "sha256:" + "a" * 64,
    }
    with pytest.raises(ValueError, match="source reviewer identity differs from handoff"):
        load_reviewer_results(
            (result_ref,), root=root, catalog={},
            digest=lambda value: "", source_review_identity=superseding_identity,
        )
    asset.write_bytes(b"wrong-asset")
    with pytest.raises(HostSourceReviewError, match="asset binding drift"):
        load_reviewer_results(
            (result_ref,), root=root, catalog={},
            digest=lambda value: "", source_review_identity=identity,
        )


def test_source_review_batch_isolates_output_failure_and_blocks_only_zero_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "output"
    (root / "inputs").mkdir(parents=True)
    (root / "inputs/metadata-catalog.json").write_text("{}", encoding="utf-8")
    for candidate_id in ("bad", "ok"):
        path = root / f"requests/{candidate_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(review_command, "OUTPUT_ROOT", root)
    monkeypatch.setattr(
        review_command,
        "guard_acquisition_source_identity",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        review_command,
        "_source_review_identity",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        review_command,
        "_validate_review_dependencies",
        lambda *_args, **_kwargs: None,
    )

    def request(path: Path, **_kwargs) -> dict:
        candidate_id = path.stem
        stable = {
            "candidateId": candidate_id,
            "contentSha256": "sha256:" + ("a" if candidate_id == "ok" else "b") * 64,
        }
        stable["requestDigest"] = "sha256:" + hashlib.sha256(
            json.dumps(
                stable,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return stable

    monkeypatch.setattr(review_command, "_review_request_with_current_contract", request)

    def review_one(candidate_id: str, _work: dict, **_kwargs) -> dict:
        if candidate_id == "bad":
            raise review_command.ProfessionalImageSupportedApiReviewError(
                "DATA.AGENT.REVIEW_INVALID: malformed reviewer output"
            )
        return {
            "candidateId": candidate_id,
            "status": "passed",
            "runId": "run-ok",
            "resultRef": "source-reviews/results/ok.json",
            "resultSha256": "sha256:" + "c" * 64,
        }

    monkeypatch.setattr(review_command, "_source_review_one", review_one)
    result = review_command.review_supported_api_inputs_from_source(
        handoff_ref=handoff,
        source_evidence_root=root,
        review_request_refs=("requests/bad.json", "requests/ok.json"),
        runner=lambda _prompt: pytest.fail("patched reviewer should be used"),
    )
    assert result["status"] == "partial"
    assert result["completedCount"] == result["excludedCount"] == 1
    assert result["results"][0]["candidateId"] == "ok"
    assert result["exclusions"][0]["failureCode"] == "DATA.AGENT.REVIEW_INVALID"

    with pytest.raises(
        review_command.ProfessionalImageSupportedApiReviewError
    ) as blocked:
        review_command.review_supported_api_inputs_from_source(
            handoff_ref=handoff,
            source_evidence_root=root,
            review_request_refs=("requests/bad.json",),
            runner=lambda _prompt: pytest.fail("patched reviewer should be used"),
        )
    assert blocked.value.code == "DATA.SOURCE.REVIEW_NO_SUCCESS"
    assert blocked.value.batch_result["status"] == "blocked"
    assert blocked.value.batch_result["excludedCount"] == 1
