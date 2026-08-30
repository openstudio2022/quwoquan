"""场景组：resource soak 观测窗口、预算与故障注入恢复统计。

从 test_campaign_scale_evidence__derived__contract__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from content.release.canonical.research_scale_promotion import (
    write_research_scale_promotion,
)
from core.paths import campaign_scale_evidence_root, research_scale_promotions_root

from support.campaign_scale_evidence_fixture import (
    START,
    _execution_id,
    _resign_receipt,
    _write,
)
from support.campaign_scale_evidence_workspace_fixture import (
    _fixture,
    _write_evidence,
)


def test_campaign_scale_evidence_derives_real_soak_faults_and_retry_chain(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    evidence, path = _write_evidence(fixture)

    assert path == (
        campaign_scale_evidence_root(output_root=fixture["output"])
        / "research-release/scale-evidence-1/campaign-scale.json"
    )
    assert evidence["status"] == "passed"
    assert evidence["targetScale"] == "M100"
    assert evidence["predecessorCarriedExecutionIds"] == []
    assert evidence["releaseExecutionIds"] == sorted(
        fixture["plan"]["executionIds"].values()
    )
    assert "predecessorPromotion" not in evidence
    assert [row["predecessorCarriedCount"] for row in evidence["lanes"]] == [0] * 4
    assert [row["newFinalizedCount"] for row in evidence["lanes"]] == [100] * 4
    assert [row["totalUniqueFinalizedCount"] for row in evidence["lanes"]] == [
        100,
        100,
        100,
        10,
    ]
    calibration_binding = evidence["calibrationPreflightReceipt"]
    assert calibration_binding["receiptRef"] == (
        fixture["calibrationPreflightReceiptPath"]
        .relative_to(fixture["output"])
        .as_posix()
    )
    calibration_receipt = json.loads(
        fixture["calibrationPreflightReceiptPath"].read_text(encoding="utf-8")
    )
    assert calibration_binding["receiptId"] == calibration_receipt["receiptId"]
    assert calibration_binding["selectionDigest"] == calibration_receipt[
        "selectionDigest"
    ]
    assert calibration_receipt["semanticSelectionId"] == "sol_calibration"
    assert calibration_receipt["provider"] == "codex_sdk"
    assert calibration_receipt["model"] == "gpt-5.6-sol"
    assert calibration_receipt["preflightReady"] is True
    assert calibration_receipt["evidence"]["semanticAgentStartup"]["ready"] is True
    assert evidence["duplicateAssetCount"] == 0
    assert evidence["crossLaneWriteCount"] == 0
    image_lane = next(row for row in evidence["lanes"] if row["carrier"] == "image")
    assert image_lane["retryChain"] == [
        _execution_id("image"),
        _execution_id("image", 1),
    ]
    assert [
        row["semanticCalibration"]["authorModel"] for row in evidence["lanes"]
    ] == ["gpt-5.6-terra"] * 4
    assert [
        row["semanticCalibration"]["reviewerModel"] for row in evidence["lanes"]
    ] == ["gpt-5.6-terra"] * 4
    assert [
        row["semanticCalibration"]["calibrationModel"] for row in evidence["lanes"]
    ] == ["gpt-5.6-sol"] * 4
    assert [
        row["semanticCalibration"]["selectionPolicy"]["requiredSampleCount"]
        for row in evidence["lanes"]
    ] == [10] * 4
    assert [
        len(row["semanticCalibration"]["calibrationRuns"])
        for row in evidence["lanes"]
    ] == [10] * 4
    resource = json.loads((path.parent / "resource-soak.json").read_text())
    fault = json.loads((path.parent / "fault-injection.json").read_text())
    assert resource["durationSeconds"] == 3720
    assert resource["fourLaneOverlapSampleCount"] == 62
    assert resource["fourLaneOverlapDurationSeconds"] == 3660
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 3660
    assert resource["allSemanticJobsTerminal"] is True
    assert resource["allSemanticJobsTerminalAt"] == (
        START + timedelta(hours=1, minutes=1)
    ).isoformat()
    assert resource["terminalResidualSampleAt"] == (
        START + timedelta(hours=1, minutes=2)
    ).isoformat()
    assert resource["terminalResidualMeasuredAfterAllJobs"] is True
    assert resource["observedPeaks"]["controllerP95RssBytes"] < 512 * 1024**2
    assert resource["observedPeaks"]["totalP95RssBytes"] < 8 * 1024**3
    assert resource["observedPeaks"]["terminalResidualBytes"] == 80 * 1024**2
    assert resource["budgets"]["maxTemporaryWorkspaceBytes"] == (
        2 * resource["releasePayloadBytes"] + 2 * 1024**3
    )
    assert [
        row["semanticJobCount"] for row in resource["semanticJobsByLane"]
    ] == [10] * 4
    assert [
        row["semanticJobSucceededCount"]
        for row in resource["semanticJobsByLane"]
    ] == [10] * 4
    assert [
        row["semanticJobTerminalCount"]
        for row in resource["semanticJobsByLane"]
    ] == [10] * 4
    assert fault["recoveryEligibleCount"] == 20
    assert fault["automaticRecoveredCount"] == 19
    assert fault["automaticRecoveryRate"] == 0.95
    assert {row["faultType"] for row in fault["casesByFaultType"]} == {
        "worker_termination",
        "lease_expiry",
        "redis_restart",
        "mongo_reconnect",
        "provider_timeout",
        "provider_rate_limit",
    }
    assert all(
        row["recoveryEligibleCount"] >= 1 for row in fault["casesByFaultType"]
    )

    promotion, promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-1",
        campaign_evidence_path=path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )
    assert promotion["targetScale"] == "M100"
    assert promotion["scaleStartedAt"] == START.isoformat()
    assert promotion["scaleCompletedAt"] == (
        START + timedelta(hours=1, minutes=2)
    ).isoformat()
    assert promotion["wallClockBudgetSeconds"] is None
    assert promotion["wallClockSeconds"] == 3720
    assert promotion["nextScaleEligible"] == "M1000"
    assert promotion["campaignEvidenceDigest"] == evidence["evidenceDigest"]
    assert promotion["carrierCounts"][-1]["targetCount"] == 10
    assert promotion["carrierCounts"][-1]["qualifiedCount"] == 10
    assert "campaignWaveStatistics" not in promotion
    assert promotion["carrierCounts"][-1]["shortfallCount"] == 0
    assert promotion["statistics"]["objectPassRate"] == {
        "numerator": 310,
        "denominator": 310,
        "rate": 1.0,
    }
    assert promotion["statistics"]["illustratedRate"] == {
        "statistical": True,
        "nonBlocking": True,
        "numerator": 90,
        "denominator": 100,
        "rate": 0.9,
    }
    assert promotion["statistics"]["textOnlyRate"] == {
        "statistical": True,
        "nonBlocking": True,
        "numerator": 10,
        "denominator": 100,
        "rate": 0.1,
    }
    assert promotion["statistics"]["automaticRecoveryRate"] == {
        "statistical": True,
        "nonBlocking": True,
        "status": "MEASURED",
        "eligibleCount": 20,
        "automaticCount": 19,
        "targetRate": 0.95,
        "rate": 0.95,
    }
    assert promotion["statistics"]["videoPopularity"]["statistical"] is True
    assert promotion["statistics"]["videoPopularity"]["nonBlocking"] is True
    assert promotion["statistics"]["videoPopularity"]["rankingCoverage"] == {
        "numerator": 10,
        "denominator": 10,
        "rate": 1.0,
    }
    assert promotion["statistics"]["videoPopularity"]["signalAvailability"] == [
        {"signal": signal, "numerator": 10, "denominator": 10, "rate": 1.0}
        for signal in ("play", "like", "comment", "share", "favorite")
    ]
    assert promotion["professionalImageSourceMix"]["acceptedImageAssetCount"] == 100
    assert promotion["professionalImageSourceMix"]["largestProvider"] == "pinterest"
    assert promotion["professionalImageSourceMix"]["pinterestAcceptedAssetCount"] == 60
    assert promotion["professionalImageSourceMix"]["tuchongAcceptedAssetCount"] == 40
    assert "firstPassRate" not in promotion["statistics"]
    assert "discardRate" not in promotion["statistics"]
    assert promotion["fourLaneOverlapDurationSeconds"] == 3660
    assert promotion["fourLaneLongestContinuousOverlapSeconds"] == 3660
    assert promotion["allSemanticJobsTerminalAt"] == resource[
        "allSemanticJobsTerminalAt"
    ]
    assert promotion["terminalResidualSampleAt"] == resource[
        "terminalResidualSampleAt"
    ]
    assert promotion_path == (
        research_scale_promotions_root(output_root=fixture["output"])
        / "research-release/promotion-1/research-m100.json"
    )
    assert promotion_path.is_file()

    repeated, repeated_path = _write_evidence(fixture)
    assert repeated == evidence
    assert repeated_path == path


def test_zero_recovery_denominator_is_nonblocking_statistic(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    for receipt_path in fixture["faultsRoot"].glob("*/receipt.json"):
        payload = json.loads(receipt_path.read_text())
        payload.update(
            {
                "actionStatus": "failed",
                "actionResultCode": "DATA.RUNTIME_EVIDENCE.FIXTURE_FAILED",
                "faultEventAt": None,
                "eventRef": None,
                "eventSha256": None,
                "queueEventEvidenceDigest": None,
            }
        )
        _write(receipt_path, payload)
        _resign_receipt(receipt_path)

    evidence, path = _write_evidence(fixture)
    fault = json.loads((path.parent / "fault-injection.json").read_text())
    assert evidence["status"] == "passed"
    assert fault["status"] == "passed"
    assert fault["automaticRecoveryStatus"] == "NOT_EXERCISED"
    assert fault["automaticRecoveryRate"] is None

    promotion, _promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-statistical-recovery",
        campaign_evidence_path=path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )
    statistic = promotion["statistics"]["automaticRecoveryRate"]
    assert statistic["nonBlocking"] is True
    assert statistic["status"] == "NOT_EXERCISED"
    assert statistic["rate"] is None


def test_low_automatic_recovery_rate_is_nonblocking_statistic(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    for receipt_path in fixture["faultsRoot"].glob("*/receipt.json"):
        if receipt_path.parent.name.endswith("-0"):
            continue
        payload = json.loads(receipt_path.read_text())
        payload.update(
            {
                "actionStatus": "failed",
                "actionResultCode": "DATA.RUNTIME_EVIDENCE.FIXTURE_FAILED",
                "faultEventAt": None,
                "eventRef": None,
                "eventSha256": None,
                "queueEventEvidenceDigest": None,
            }
        )
        _write(receipt_path, payload)
        _resign_receipt(receipt_path)

    evidence, path = _write_evidence(fixture)
    fault = json.loads((path.parent / "fault-injection.json").read_text())

    assert evidence["status"] == "passed"
    assert fault["status"] == "passed"
    assert fault["recoveryEligibleCount"] == 4
    assert fault["automaticRecoveredCount"] == 3
    assert fault["automaticRecoveryRate"] == 0.75

    promotion, _promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-low-statistical-recovery",
        campaign_evidence_path=path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )
    statistic = promotion["statistics"]["automaticRecoveryRate"]
    assert statistic["nonBlocking"] is True
    assert statistic["eligibleCount"] == 4
    assert statistic["rate"] == 0.75


def test_resource_soak_requires_one_continuous_four_lane_hour(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    video_queue = (
        fixture["tasks"]
        / _execution_id("video")
        / "_shared/object_queue"
    )
    shortened_terminal = (START + timedelta(minutes=30)).isoformat()
    for job_path in video_queue.glob("*.json"):
        job = json.loads(job_path.read_text())
        job["timings"][-1]["at"] = shortened_terminal
        job["updatedAt"] = shortened_terminal
        _write(job_path, job)

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["fourLaneOverlapSampleCount"] > 1
    assert resource["fourLaneOverlapDurationSeconds"] == 1800
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 1800
    assert resource["status"] == "failed"
    assert evidence["status"] == "passed"


def test_resource_soak_requires_observation_window_to_cover_four_lane_hour(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    shifted_start = START + timedelta(hours=1, seconds=30)
    for index, receipt_path in enumerate(
        sorted(fixture["samplesRoot"].glob("*.json"))
    ):
        payload = json.loads(receipt_path.read_text())
        captured_at = shifted_start + timedelta(minutes=index)
        payload["capturedAt"] = captured_at.isoformat()
        payload["rawSample"]["capturedAt"] = captured_at.isoformat()
        payload["queueMeasurements"][0]["oldestReadyAt"] = (
            captured_at - timedelta(seconds=300)
        ).isoformat() if payload["rawSample"]["queueDepth"] else None
        _write(receipt_path, payload)
        _resign_receipt(receipt_path)

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["fourLaneOverlapSampleCount"] == 1
    assert resource["fourLaneOverlapDurationSeconds"] == 30
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 30
    assert resource["status"] == "failed"
    assert evidence["status"] == "passed"
    promotion, _promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-observation-window-diagnostic",
        campaign_evidence_path=path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )
    assert promotion["statistics"]["resourceSoak"] == {
        "statistical": True,
        "nonBlocking": True,
        "status": "failed",
        "durationSeconds": resource["durationSeconds"],
        "fourLaneOverlapDurationSeconds": 30,
    }
    assert [row["shortfallCount"] for row in promotion["carrierCounts"]] == [0] * 4


def test_resource_soak_rejects_sampling_gap_inside_four_lane_hour(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    sorted(fixture["samplesRoot"].glob("*.json"))[30].unlink()

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["maxSampleGapSeconds"] == 120
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 3660
    assert resource["status"] == "failed"
    assert evidence["status"] == "passed"


def test_resource_soak_requires_residual_sample_after_every_job_terminal(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    for path in sorted(fixture["samplesRoot"].glob("*.json"))[61:]:
        path.unlink()

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["durationSeconds"] == 3600
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 3600
    assert resource["allSemanticJobsTerminal"] is True
    assert resource["terminalResidualMeasuredAfterAllJobs"] is False
    assert resource["status"] == "failed"
    assert evidence["status"] == "passed"


def test_resource_soak_requires_residual_sample_strictly_after_all_jobs(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    for path in sorted(fixture["samplesRoot"].glob("*.json"))[62:]:
        path.unlink()

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["allSemanticJobsTerminalAt"] == resource[
        "terminalResidualSampleAt"
    ]
    assert resource["terminalResidualMeasuredAfterAllJobs"] is False
    assert resource["status"] == "failed"
    assert evidence["status"] == "passed"


def test_resource_soak_counts_non_terminal_semantic_job_fail_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    job_path = (
        fixture["tasks"]
        / _execution_id("article")
        / "_shared/object_queue/ar-semantic-09.json"
    )
    job = json.loads(job_path.read_text())
    job["state"] = "failed"
    _write(job_path, job)

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())
    article = resource["semanticJobsByLane"][1]

    assert article["semanticJobCount"] == 10
    assert article["semanticJobSucceededCount"] == 9
    assert article["semanticJobTerminalCount"] == 9
    assert resource["allSemanticJobsTerminal"] is False
    assert resource["allSemanticJobsTerminalAt"] is None
    assert resource["status"] == "failed"
    assert evidence["status"] == "passed"


def test_resource_soak_enforces_hard_rss_and_terminal_cleanup_budgets(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    sample_path = max(fixture["samplesRoot"].glob("*.json"))
    payload = json.loads(sample_path.read_text())
    other_rss = sum(
        int(row["rssBytes"])
        for row in payload["processMeasurements"]
        if row["carrier"] != "video"
    )
    video = next(
        row for row in payload["processMeasurements"] if row["carrier"] == "video"
    )
    video["rssBytes"] = 11 * 1024**3 - other_rss
    payload["rawSample"]["videoWorkerMaxRssBytes"] = video["rssBytes"]
    payload["rawSample"]["totalRssBytes"] = 11 * 1024**3
    payload["rawSample"]["terminalResidualBytes"] = 101 * 1024**2
    staging = next(
        row
        for row in payload["workspaceMeasurements"]
        if row["kind"] == "transaction_staging"
    )
    execution = next(
        row
        for row in payload["workspaceMeasurements"]
        if row["kind"] == "execution"
    )
    staging["bytes"] = 101 * 1024**2
    execution["bytes"] = (
        payload["rawSample"]["temporaryWorkspaceBytes"] - staging["bytes"]
    )
    _write(sample_path, payload)
    _resign_receipt(sample_path)

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert evidence["status"] == "passed"
    assert resource["status"] == "failed"
    assert set(resource["budgetBreaches"]) == {
        "totalMaxRssBytes",
        "terminalResidualBytes",
    }
