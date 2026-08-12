from __future__ import annotations

import json
from pathlib import Path

from content.execution.agent.outcome import AgentRunOutcome
from content.execution.controller.execute import author_image_supported_api_input as subject
from core.control_types import AgentProvider


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
