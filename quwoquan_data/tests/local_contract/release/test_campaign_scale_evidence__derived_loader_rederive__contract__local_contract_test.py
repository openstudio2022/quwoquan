"""场景组：loader 对子证据重派生防篡改与 release CLI writer 入口。

从 test_campaign_scale_evidence__derived__contract__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from content.release.canonical.campaign_scale_evidence import (
    CampaignScaleEvidenceError,
    load_campaign_scale_evidence,
)
from content.release.canonical.handler import register_parser
from content.release.canonical.research_scale_promotion import (
    ResearchScalePromotionError,
    write_research_scale_promotion,
)
from support.campaign_scale_evidence_fixture import (
    _execution_id,
    _resign_evidence,
    _write,
)
from support.campaign_scale_evidence_workspace_fixture import (
    _fixture,
    _write_evidence,
)


def test_campaign_loader_rederives_resource_evidence_after_valid_resign(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    resource_path = path.parent / "resource-soak.json"
    resource = json.loads(resource_path.read_text())
    resource["fourLaneOverlapDurationSeconds"] += 60
    _write(resource_path, resource)
    resigned_resource = _resign_evidence(resource_path)
    campaign = json.loads(path.read_text())
    campaign["resourceSoakEvidenceDigest"] = resigned_resource["evidenceDigest"]
    campaign["fourLaneOverlapDurationSeconds"] = resigned_resource[
        "fourLaneOverlapDurationSeconds"
    ]
    _write(path, campaign)
    _resign_evidence(path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="resource soak derived evidence drift",
    ):
        load_campaign_scale_evidence(
            path,
            output_root=fixture["output"],
            diagnostics_required=True,
        )


def test_campaign_loader_rederives_aggregate_after_valid_resign(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    campaign = json.loads(path.read_text())
    campaign["articleIllustratedRate"] = 0.95
    _write(path, campaign)
    _resign_evidence(path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="campaign exact promotion closure drift",
    ):
        load_campaign_scale_evidence(
            path,
            output_root=fixture["output"],
            diagnostics_required=True,
        )


def test_campaign_loader_rederives_fault_evidence_after_valid_resign(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    fault_path = path.parent / "fault-injection.json"
    fault = json.loads(fault_path.read_text())
    fault["automaticRecoveredCount"] = 20
    fault["manualRecoveredCount"] = 0
    fault["automaticRecoveryRate"] = 1.0
    for case in fault["cases"]:
        if case["outcome"] == "manual":
            case["outcome"] = "automatic"
    _write(fault_path, fault)
    resigned_fault = _resign_evidence(fault_path)
    campaign = json.loads(path.read_text())
    campaign["faultInjectionEvidenceDigest"] = resigned_fault["evidenceDigest"]
    _write(path, campaign)
    _resign_evidence(path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="create-once fault_injection_evidence collision",
    ):
        load_campaign_scale_evidence(
            path,
            output_root=fixture["output"],
            diagnostics_required=True,
        )


def test_fault_injection_records_typed_event_digest_drift_without_blocking(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    receipt_path = min(fixture["faultsRoot"].glob("*/receipt.json"))
    receipt = json.loads(receipt_path.read_text())
    event_path = fixture["output"] / receipt["eventRef"]
    event = json.loads(event_path.read_text())
    event["faultType"] = "provider_timeout"
    _write(event_path, event)

    evidence, _path = _write_evidence(fixture)

    assert evidence["status"] == "passed"
    assert "resourceSoakEvidenceRef" not in evidence
    assert "faultInjectionEvidenceRef" not in evidence
    assert any(
        "RUNTIME_EVIDENCE_UNAVAILABLE" in issue
        for issue in evidence["diagnosticIssues"]
    )


def test_campaign_scale_evidence_marks_cross_lane_write_failed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    publish_path = fixture["tasks"] / _execution_id("article") / "publish_ref.json"
    publish = json.loads(publish_path.read_text())
    publish["publishedRefs"]["posts"][-1] = "image/测试/cross-lane/001"
    _write(publish_path, publish)

    evidence, _ = _write_evidence(fixture)

    assert evidence["status"] == "failed"
    assert evidence["crossLaneWriteCount"] == 1


def test_promotion_ignores_invalid_subordinate_diagnostic_digest(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    resource_path = path.parent / "resource-soak.json"
    resource = json.loads(resource_path.read_text())
    resource["fourLaneOverlapSampleCount"] = 60
    _write(resource_path, resource)

    promotion, _promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-diagnostics-unavailable",
        campaign_evidence_path=path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )

    assert [row["shortfallCount"] for row in promotion["carrierCounts"]] == [0] * 4
    assert "resourceSoakEvidenceRef" not in promotion
    assert any(
        "RESOURCE_SOAK_UNAVAILABLE" in issue
        or "SCALE_TIMING_UNAVAILABLE" in issue
        for issue in promotion["diagnosticIssues"]
    )


def test_release_cli_exposes_canonical_campaign_scale_evidence_writer() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    register_parser(commands)

    parsed = parser.parse_args(
        [
            "release",
            "campaign-scale-evidence",
            "--evidence-id",
            "evidence-1",
            "--release-id",
            "research-release",
            "--target-scale",
            "M1000",
            "--predecessor-promotion",
            "/tmp/m100-promotion.json",
            "--campaign-plan",
            "/tmp/campaign-plan.json",
            "--runtime-session",
            "/tmp/runtime-session.json",
            "--calibration-preflight-receipt",
            "/tmp/sol-calibration-preflight.json",
        ]
    )

    assert parsed.release_command == "campaign-scale-evidence"
    assert parsed.evidence_id == "evidence-1"
    assert parsed.target_scale == "M1000"
    assert parsed.predecessor_promotion == "/tmp/m100-promotion.json"
    assert parsed.runtime_session == "/tmp/runtime-session.json"
    assert parsed.calibration_preflight_receipt == (
        "/tmp/sol-calibration-preflight.json"
    )

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "release",
                "campaign-scale-evidence",
                "--evidence-id",
                "handwritten-raw",
                "--release-id",
                "research-release",
                "--campaign-plan",
                "/tmp/campaign-plan.json",
                "--resource-samples",
                "/tmp/handwritten-samples.json",
                "--fault-cases",
                "/tmp/handwritten-faults.json",
            ]
        )
