"""Canonical campaign preparation freezes only governed four-lane inputs."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest
from content.execution.campaign import prepare as prepare_campaign
from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from core.io import write_json


def _args(tmp_path: Path) -> Namespace:
    return Namespace(
        phase="envelopes",
        scale="M3",
        region_ref="china",
        run_date="20260806",
        sequence=2,
        topic="川西",
        target_names=["四姑娘山", "九寨沟"],
        source_providers=["pinterest", "manual_file"],
        semantic_selection_id="default",
        semantic_preflight_receipt=str(tmp_path / "semantic-preflight.json"),
        handoff_id=None,
        handoff_revision=None,
        supersedes_handoff_ref=None,
        campaign_retry_of=None,
        handoff_ref=str(tmp_path / "handoff.json"),
        predecessor_reconciliation_receipt=None,
        promotion_receipt=None,
        homepage_retry_of="20260805--travel-homepage-m3--china--scale-001",
        article_retry_of="20260805--travel-article-m3--china--scale-001",
        image_retry_of="20260805--travel-image-m3--china--scale-001",
        video_retry_of="20260805--travel-video-m3--china--scale-001",
        homepage_image_input=[["home/manifest.json", "home/receipts/r.json"]],
        image_input=[["image/manifest.json", "image/receipts/r.json"]],
        video_input=[["video/manifest.json", "video/receipts/r.json"]],
    )


def _fake_envelopes(tmp_path: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for carrier in CAMPAIGN_CARRIERS:
        path = tmp_path / f"{carrier}.json"
        write_json(
            path,
            {
                "scale": "M3",
                "rootExecutionId": (
                    "20260806--travel-homepage-m3--china--scale-002"
                ),
                "executionId": f"20260806--travel-{carrier}-m3--china--scale-002",
                "retryOf": f"20260805--travel-{carrier}-m3--china--scale-001",
                "familyRef": f"content/travel/{carrier}/{carrier}",
                "regionRef": "china",
                "selector": "all",
                "quota": 3,
                "count": 6,
                "requiredWorkers": 1,
                "partitionCount": 16,
                "capacityPlanDigest": "sha256:" + "9" * 64,
                "topic": "川西",
                "targetNames": ["九寨沟", "四姑娘山"],
                "sourceProviders": ["manual_file", "pinterest"],
                "sourceRevision": "sha256:" + "a" * 64,
                "sourceDigest": {"digest": "sha256:" + "b" * 64},
                "entityCatalogDigest": "sha256:" + "c" * 64,
                "preAcquisitionHandoff": {
                    "handoffId": "m3-test",
                    "handoffRevision": 1,
                    "handoffRef": "data/local/workspace/handoff.json",
                    "handoffDigest": "sha256:" + "e" * 64,
                    "handoffFileDigest": "sha256:" + "f" * 64,
                },
                "semanticSelectionId": "default",
                "semanticPreflightReceipt": {"receiptRef": "preflight.json"},
                "requestDigest": "sha256:" + "d" * 64,
            },
        )
        paths[carrier] = path
    return paths


def test_prepare_campaign_maps_only_governed_external_input_kinds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    paths = _fake_envelopes(tmp_path)

    def write_scale(scale: str, **kwargs: object) -> dict[str, Path]:
        captured["scale"] = scale
        captured.update(kwargs)
        return paths

    monkeypatch.setattr(prepare_campaign, "write_scale_envelopes", write_scale)
    prepare_campaign.handle_prepare_campaign(_args(tmp_path))

    assert captured["scale"] == "M3"
    assert captured["semantic_selection_id"] == "default"
    assert captured["semantic_preflight_receipt"] == (
        tmp_path / "semantic-preflight.json"
    ).resolve()
    assert captured["pre_acquisition_handoff"] == (
        tmp_path / "handoff.json"
    ).resolve()
    assert captured["predecessor_execution_ids_by_carrier"] == {
        carrier: f"20260805--travel-{carrier}-m3--china--scale-001"
        for carrier in CAMPAIGN_CARRIERS
    }
    assert captured["external_input_refs_by_carrier"] == {
        "homepage": [
            {
                "kind": "professional_image_acquisition",
                "acquisitionRootRef": ".",
                "manifestRef": "home/manifest.json",
                "receiptRef": "home/receipts/r.json",
            }
        ],
        "article": [],
        "image": [
            {
                "kind": "professional_image_acquisition",
                "acquisitionRootRef": ".",
                "manifestRef": "image/manifest.json",
                "receiptRef": "image/receipts/r.json",
            }
        ],
        "video": [
            {
                "kind": "professional_video_acquisition",
                "acquisitionRootRef": "video",
                "manifestRef": "video/manifest.json",
                "receiptRef": "video/receipts/r.json",
            }
        ],
    }
    output = capsys.readouterr().out
    assert "campaign_envelope_prepare_result" in output
    assert '"articleExternalInputMode": "execution_source_unit_freeze"' in output
    assert '"campaign-freeze"' in output
    assert '"campaign-lane-run"' in output
    assert '"campaign-finalize"' in output


def test_prepare_campaign_reports_writer_failure_as_gate_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prepare_campaign,
        "write_scale_envelopes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("preflight receipt expired")
        ),
    )
    with pytest.raises(SystemExit, match="GATE_BLOCK.*preflight receipt expired"):
        prepare_campaign.handle_prepare_campaign(_args(tmp_path))


def test_prepare_campaign_handoff_revision_never_writes_envelopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args(tmp_path)
    args.phase = "handoff"
    args.handoff_id = "travel-m100-20260807"
    args.handoff_revision = 2
    args.supersedes_handoff_ref = str(tmp_path / "manual-revision-1.json")
    args.campaign_retry_of = None
    args.handoff_ref = None
    args.semantic_preflight_receipt = None
    args.homepage_image_input = None
    args.image_input = None
    args.video_input = None
    for carrier in CAMPAIGN_CARRIERS:
        setattr(args, f"{carrier}_retry_of", None)
    observed: list[str] = []
    monkeypatch.setattr(
        prepare_campaign,
        "_handle_handoff",
        lambda _args: observed.append("handoff"),
    )
    monkeypatch.setattr(
        prepare_campaign,
        "_handle_envelopes",
        lambda _args: pytest.fail("handoff phase must not create envelopes"),
    )

    prepare_campaign.handle_prepare_campaign(args)

    assert observed == ["handoff"]


def test_prepare_campaign_envelopes_require_explicit_handoff(tmp_path: Path) -> None:
    args = _args(tmp_path)
    args.handoff_ref = None

    with pytest.raises(SystemExit, match="GATE_BLOCK.*--handoff-ref"):
        prepare_campaign.handle_prepare_campaign(args)
