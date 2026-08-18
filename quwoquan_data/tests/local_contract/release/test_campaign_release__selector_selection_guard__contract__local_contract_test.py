"""场景组：selection attestation 冲突与 publish/runtime 绑定阻断。

从 test_campaign_release__selector__contract__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from content.release.canonical import campaign_release
from content.release.canonical.campaign_release import (
    CampaignReleaseError,
    CampaignReleaseRoots,
    build_campaign_release,
)
from core.release_layout import payload_digest

from support.campaign_release_selector_fixture import (
    RELEASE_ID,
    _digest,
    _fixture,
    _write,
)


def test_campaign_release__missing_publish_binding_fails_schema_before_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    campaign_root = fixture["campaignRoot"]
    assert isinstance(campaign_root, Path)
    receipt_path = campaign_root / "receipts/image-publish.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("executionPublishRef")
    _write(receipt_path, receipt)
    called = False

    def aggregate(**_kwargs: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(campaign_release, "build_aggregate_release", aggregate)
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            release_class="research",
            roots=fixture["roots"],
        )

    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_PUBLISH_RECEIPT_INVALID"
    assert "executionPublishRef" in str(caught.value)
    assert called is False


def test_campaign_release__conflicting_self_consistent_selection_blocks_before_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)

    def initial_aggregate(**kwargs: object) -> dict[str, object]:
        release = Path(kwargs["release_root"]) / str(kwargs["release_id"])
        _write(release / "payload/release.json", {"releaseId": RELEASE_ID})
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(release),
            "executionIds": list(kwargs["execution_ids"]),
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": False,
        }

    monkeypatch.setattr(campaign_release, "build_aggregate_release", initial_aggregate)
    initial = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        release_class="research",
        roots=roots,
    )
    selection_path = Path(initial["campaignSelectionAttestation"])
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection["releaseId"] = "conflicting-release-id"
    selection["selectionDigest"] = _digest(
        {key: value for key, value in selection.items() if key != "selectionDigest"}
    )
    _write(selection_path, selection)
    target_release = roots.release_root / RELEASE_ID
    shutil.rmtree(target_release)

    aggregate_calls = 0

    def forbidden_aggregate(**_kwargs: object) -> dict[str, object]:
        nonlocal aggregate_calls
        aggregate_calls += 1
        raise AssertionError("conflicting selection must block before aggregate")

    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        forbidden_aggregate,
    )
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            release_class="research",
            roots=roots,
        )

    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_ATTESTATION_CONFLICT"
    assert aggregate_calls == 0
    assert not target_release.exists()


def test_campaign_release__selection_extra_field_blocks_before_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)

    def initial_aggregate(**kwargs: object) -> dict[str, object]:
        release = Path(kwargs["release_root"]) / str(kwargs["release_id"])
        _write(release / "payload/release.json", {"releaseId": RELEASE_ID})
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(release),
            "executionIds": list(kwargs["execution_ids"]),
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": False,
        }

    monkeypatch.setattr(campaign_release, "build_aggregate_release", initial_aggregate)
    initial = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        release_class="research",
        roots=roots,
    )
    selection_path = Path(initial["campaignSelectionAttestation"])
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection["unexpectedEvidence"] = {"accepted": True}
    selection["selectionDigest"] = _digest(
        {key: value for key, value in selection.items() if key != "selectionDigest"}
    )
    _write(selection_path, selection)
    target_release = roots.release_root / RELEASE_ID
    shutil.rmtree(target_release)

    aggregate_calls = 0

    def forbidden_aggregate(**_kwargs: object) -> dict[str, object]:
        nonlocal aggregate_calls
        aggregate_calls += 1
        raise AssertionError("selection with extra keys must block before aggregate")

    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        forbidden_aggregate,
    )
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            release_class="research",
            roots=roots,
        )

    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_ATTESTATION_CONFLICT"
    assert aggregate_calls == 0
    assert not target_release.exists()


def test_campaign_release__existing_release_without_selection_backfills_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)
    target_release = roots.release_root / RELEASE_ID
    _write(target_release / "payload/release.json", {"releaseId": RELEASE_ID})
    aggregate_calls = 0

    def idempotent_aggregate(**kwargs: object) -> dict[str, object]:
        nonlocal aggregate_calls
        aggregate_calls += 1
        assert (
            Path(kwargs["release_root"]) / str(kwargs["release_id"]) == target_release
        )
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(target_release),
            "executionIds": list(kwargs["execution_ids"]),
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": True,
        }

    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        idempotent_aggregate,
    )
    result = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        release_class="research",
        roots=roots,
    )
    selection_path = Path(result["campaignSelectionAttestation"])
    selection = json.loads(selection_path.read_text(encoding="utf-8"))

    assert aggregate_calls == 1
    assert result["idempotent"] is True
    assert selection["releaseId"] == RELEASE_ID
    assert selection["manifestDigest"] == payload_digest(target_release)
    assert selection_path.is_file()


def test_campaign_release__publish_ref_digest_tamper_blocks_aggregate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    image_id = fixture["executionIds"]["image"]
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)
    publish_path = roots.tasks_root / image_id / "publish_ref.json"
    publish = json.loads(publish_path.read_text(encoding="utf-8"))
    publish["publishedRefs"]["posts"].append("image/测试/injected/001")
    _write(publish_path, publish)

    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        lambda **_kwargs: pytest.fail("aggregate must not run"),
    )
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            release_class="research",
            roots=roots,
        )
    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_PUBLISH_BINDING_DRIFT"


def test_campaign_release__stale_runtime_checkpoint_blocks_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    campaign_root = fixture["campaignRoot"]
    assert isinstance(campaign_root, Path)
    checkpoint_path = campaign_root / "runtime/lanes/video.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["generation"] = 2
    _write(checkpoint_path, checkpoint)
    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        lambda **_kwargs: pytest.fail("aggregate must not run"),
    )

    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            release_class="research",
            roots=fixture["roots"],
        )
    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_FENCE_DRIFT"
