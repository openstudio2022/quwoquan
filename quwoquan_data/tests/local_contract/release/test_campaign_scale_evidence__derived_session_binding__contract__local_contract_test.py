"""场景组：runtime session、回执与 Sol calibration 的身份绑定拒绝。

从 test_campaign_scale_evidence__derived__contract__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.execution.scale.semantic_promotion import (
    select_scale_calibration_refs,
    semantic_calibration_evidence_path,
)
from content.release.canonical.campaign_scale_evidence import (
    CampaignScaleEvidenceError,
    load_campaign_scale_evidence,
)
from support.semantic_preflight_fixture import ready_semantic_preflight

from support.campaign_scale_evidence_fixture import (
    _execution_id,
    _publish_refs,
    _resign_receipt,
    _write,
)
from support.campaign_scale_evidence_workspace_fixture import (
    _fixture,
    _write_evidence,
)


def test_campaign_scale_evidence_blocks_lane_receipt_identity_drift(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    receipt = fixture["campaignRoot"] / "receipts/image-publish.json"
    payload = json.loads(receipt.read_text())
    payload["executionId"] = _execution_id("image", 1)
    _write(receipt, payload)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="publish receipt identity drift",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_terra_capacity_as_sol_calibration(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    terra_receipt_path, _terra_binding = ready_semantic_preflight(
        "default",
        output_root=fixture["output"],
    )

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="Sol calibration preflight receipt is not promotable.*expected selection",
    ):
        _write_evidence(
            fixture,
            calibration_preflight_receipt_path=terra_receipt_path,
        )


def test_campaign_scale_loader_rejects_missing_sol_preflight_binding(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["calibrationPreflightReceipt"]
    _write(path, payload)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match=r"(?s)schema violation:.*calibrationPreflightReceipt",
    ):
        load_campaign_scale_evidence(path, output_root=fixture["output"])


def test_campaign_scale_loader_rejects_sol_preflight_file_digest_drift(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    receipt_path = fixture["calibrationPreflightReceiptPath"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["validUntil"] = "2099-01-01T00:00:00Z"
    _write(receipt_path, receipt)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="bound Sol calibration preflight receipt is invalid.*file digest drift",
    ):
        load_campaign_scale_evidence(path, output_root=fixture["output"])


def test_campaign_scale_evidence_rejects_cross_session_sample_receipt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    sample_path = min(fixture["samplesRoot"].glob("*.json"))
    sample = json.loads(sample_path.read_text())
    sample["runId"] = "different-runtime-run"
    _write(sample_path, sample)
    _resign_receipt(sample_path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="resource sample/session identity drift",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_duplicate_sample_timestamp(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    sample_paths = sorted(fixture["samplesRoot"].glob("*.json"))
    first = json.loads(sample_paths[0].read_text())
    second = json.loads(sample_paths[1].read_text())
    second["capturedAt"] = first["capturedAt"]
    second["rawSample"]["capturedAt"] = first["capturedAt"]
    second["queueMeasurements"][0]["oldestReadyAt"] = first[
        "queueMeasurements"
    ][0]["oldestReadyAt"]
    _write(sample_paths[1], second)
    _resign_receipt(sample_paths[1])

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="duplicate identity or timestamp",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_runtime_session_source_drift(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    session_path = fixture["sessionPath"]
    session = json.loads(session_path.read_text())
    session["sourceDigest"] = "sha256:" + "0" * 64
    _write(session_path, session)
    _resign_receipt(session_path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="runtime session campaign identity drift",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_cross_session_fault_receipt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    receipt_path = min(fixture["faultsRoot"].glob("*/receipt.json"))
    receipt = json.loads(receipt_path.read_text())
    receipt["generation"] = 2
    _write(receipt_path, receipt)
    _resign_receipt(receipt_path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="fault case/session identity drift",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_auto_model_binding_at_manifest_contract(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    manifest_path = fixture["tasks"] / _execution_id("image") / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["modelBinding"].update(
        {
            "provider": "cursor_sdk",
            "authorModel": "auto",
            "authorModelFamily": "auto",
            "reviewerModel": "auto",
            "reviewerModelFamily": "auto",
        }
    )
    _write(manifest_path, manifest)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="schema violation",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_blocks_same_author_reviewer_run(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    object_root = (
        fixture["tasks"]
        / _execution_id("video")
        / "posts/video/测试/test-000/001"
    )
    author = json.loads(
        (object_root / "4.draft/agent_result_envelope.json").read_text()
    )
    reviewer_path = object_root / "5.review/reviewer_result.json"
    reviewer = json.loads(reviewer_path.read_text())
    reviewer["runId"] = author["agent"]["runId"]
    _write(reviewer_path, reviewer)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="DATA.AGENT.SCALE_CALIBRATION_REQUIRED",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_blocks_missing_sol_calibration_sample(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    carrier = "article"
    refs = [
        f"posts/{ref}"
        for ref in _publish_refs(carrier)["posts"]
    ]
    selected = select_scale_calibration_refs(
        carrier=carrier,
        object_refs=refs,
        accepted_count=100,
    )
    semantic_calibration_evidence_path(
        fixture["tasks"] / _execution_id(carrier),
        object_ref=selected[0],
    ).unlink()

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="DATA.AGENT.SCALE_CALIBRATION_REQUIRED",
    ):
        _write_evidence(fixture)
