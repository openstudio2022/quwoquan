from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.controller.execute import author_image_supported_api_input as subject
from core.control_types import AgentProvider
from content.execution.model_contract import governed_cursor_grok_model


def test_cli_exposes_explicit_acquisition_and_asset_ids() -> None:
    import argparse
    from content.execution.handler import register_parser

    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="root", required=True))
    args = parser.parse_args([
        "task", "author-image-supported-api-input",
        "--execution-id", "20260812--travel-image-author--china--pilot-001",
        "--acquisition-root", "/tmp/acquisition",
        "--acquisition-receipt-ref", "receipts/exact.json",
        "--asset-id", "openverse:asset:a",
        "--asset-id", "openverse:asset:b",
    ])
    assert args.asset_id == ["openverse:asset:a", "openverse:asset:b"]
    assert not hasattr(args, "verdict")
    assert not hasattr(args, "run_id")


def test_author_result_parser_requires_exact_contract() -> None:
    valid = {
        "schema": "quwoquan_data.professional_image_supported_api_author_result",
        "candidateId": "openverse:asset:a",
        "contentSha256": "sha256:" + "a" * 64,
        "entityId": "乌镇", "status": "passed", "entityMatch": "matched",
        "attributionMatch": "matched", "qualityStatus": "passed",
        "caption": "乌镇水巷与白墙黛瓦。", "findings": ["visible canal"],
    }
    assert subject._author_result(json.dumps(valid, ensure_ascii=False)) == valid
    assert subject._author_result(json.dumps({**valid, "verdict": "passed"})) is None


def test_prompt_freezes_asset_identity_and_untrusted_media_rule() -> None:
    asset = {
        "assetId": "openverse:asset:a", "contentSha256": "sha256:" + "a" * 64,
        "entityId": "乌镇", "sourceAttribution": {"platform": "Openverse"},
    }
    prompt = subject._prompt(asset, staged_asset_ref="input/asset.jpg")
    assert "untrusted evidence" in prompt
    assert asset["assetId"] in prompt and asset["contentSha256"] in prompt


def test_runner_outcome_must_be_real_provider_identity() -> None:
    outcome = AgentRunOutcome.finished(
        provider=AgentProvider.CURSOR_SDK,
        run_id="run-real-author", result_text="{}",
    )
    assert outcome.provider is AgentProvider.CURSOR_SDK
    assert outcome.run_id == "run-real-author"


def test_author_batch_keeps_success_and_types_failed_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {"ok": {"assetId": "ok"}, "bad": {"assetId": "bad"}}
    monkeypatch.setattr(
        subject,
        "_author_inputs",
        lambda **_kwargs: (
            rows,
            SimpleNamespace(),
            SimpleNamespace(model_id=governed_cursor_grok_model()),
            tmp_path / "workspace",
            tmp_path / "acquisition",
        ),
    )

    def author_one(asset_id: str, _asset: dict, **_kwargs) -> dict:
        if asset_id == "bad":
            raise subject.ProfessionalImageSupportedApiAuthorError(
                "DATA.AGENT.AUTHOR_FAILED: provider_failure"
            )
        return {
            "assetId": asset_id,
            "objectRef": f"/professional-image/{asset_id}",
            "runId": "run-ok",
            "envelopeRef": "data/tasks/ok/envelope.json",
            "envelopeSha256": "sha256:" + "a" * 64,
        }

    monkeypatch.setattr(subject, "_author_one", author_one)
    result = subject.author_supported_api_images(
        execution_id="execution",
        acquisition_root=tmp_path,
        acquisition_receipt_ref="receipts/input.json",
        asset_ids=("bad", "ok"),
        runner=lambda _context, _prompt: pytest.fail("patched author should be used"),
    )
    assert result["status"] == "partial"
    assert result["completedCount"] == result["excludedCount"] == 1
    assert result["results"][0]["assetId"] == "ok"
    assert result["exclusions"] == [
        {
            "assetId": "bad",
            "failureCode": "DATA.AGENT.AUTHOR_FAILED",
            "failure": "provider_failure",
        }
    ]


def test_author_zero_success_blocks_but_create_once_conflict_stays_global(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "_author_inputs",
        lambda **_kwargs: (
            {"bad": {"assetId": "bad"}},
            SimpleNamespace(),
            SimpleNamespace(model_id=governed_cursor_grok_model()),
            tmp_path / "workspace",
            tmp_path / "acquisition",
        ),
    )
    monkeypatch.setattr(
        subject,
        "_author_one",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subject.ProfessionalImageSupportedApiAuthorError(
                "DATA.AGENT.AUTHOR_INVALID: malformed model output"
            )
        ),
    )
    with pytest.raises(subject.ProfessionalImageSupportedApiAuthorError) as blocked:
        subject.author_supported_api_images(
            execution_id="execution",
            acquisition_root=tmp_path,
            acquisition_receipt_ref="receipts/input.json",
            asset_ids=("bad",),
            runner=lambda _context, _prompt: pytest.fail("patched author should be used"),
        )
    assert blocked.value.code == "DATA.SOURCE.AUTHOR_NO_SUCCESS"
    assert blocked.value.batch_result["status"] == "blocked"
    assert blocked.value.batch_result["excludedCount"] == 1

    monkeypatch.setattr(
        subject,
        "_author_one",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subject.ProfessionalImageSupportedApiAuthorError(
                "DATA.SOURCE.AUTHOR_CREATE_ONCE_CONFLICT: existing output differs",
                batch_fatal=True,
            )
        ),
    )
    with pytest.raises(subject.ProfessionalImageSupportedApiAuthorError) as fatal:
        subject.author_supported_api_images(
            execution_id="execution",
            acquisition_root=tmp_path,
            acquisition_receipt_ref="receipts/input.json",
            asset_ids=("bad",),
            runner=lambda _context, _prompt: pytest.fail("patched author should be used"),
        )
    assert fatal.value.code == "DATA.SOURCE.AUTHOR_CREATE_ONCE_CONFLICT"
    assert fatal.value.batch_fatal is True
