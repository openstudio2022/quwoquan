"""场景组：cumulative scale 上下文、wall clock 预算与 promotion 时序。

从 test_campaign_scale_evidence__derived__contract__local_contract_test.py
按场景拆出（本文件经 git mv 承接原文件历史）；测试逐字搬移。
"""
from __future__ import annotations

import inspect
import json
from datetime import timedelta
from pathlib import Path

import pytest
from content.release.canonical import campaign_scale_cumulative
from content.release.canonical import (
    campaign_scale_diagnostics as campaign_scale_diagnostics_module,
)
from content.release.canonical import (
    campaign_scale_evidence as campaign_scale_evidence_module,
)
from content.release.canonical import (
    research_scale_promotion_diagnostics as promotion_diagnostics_module,
)
from content.release.canonical.campaign_scale_evidence import (
    CampaignScaleEvidenceError,
    load_campaign_scale_evidence,
)
from content.release.canonical.campaign_scale_source_pool import (
    source_pool_lineage_fields,
)
from content.release.canonical.research_scale_promotion import (
    write_research_scale_promotion,
)
from content.release.canonical.research_scale_promotion_timing import (
    ResearchScalePromotionTimingError,
    validate_promotion_timing,
)
from core.paths import SCHEMA_ROOT
from support.campaign_scale_evidence_fixture import (
    CARRIERS,
    CATALOG_DIGEST,
    SOURCE_DIGEST,
    SOURCE_DIGEST_DOCUMENT,
    START,
    _digest,
    _execution_id,
    _file_digest,
    _write,
)
from support.campaign_scale_evidence_workspace_fixture import (
    _fixture,
    _write_evidence,
)


def test_promotion_contract_keeps_runtime_diagnostics_optional() -> None:
    campaign_schema = json.loads(
        (SCHEMA_ROOT / "release/campaign_scale_evidence.schema.json").read_text(
            encoding="utf-8"
        )
    )
    promotion_schema = json.loads(
        (SCHEMA_ROOT / "release/research_scale_promotion.schema.json").read_text(
            encoding="utf-8"
        )
    )
    loader_parameter = inspect.signature(
        campaign_scale_evidence_module.load_campaign_scale_evidence
    ).parameters["diagnostics_required"]
    campaign_diagnostics = {
        "runtimeSessionId",
        "runtimeSessionRef",
        "runtimeSessionDigest",
        "runId",
        "generation",
        "fencingToken",
        "scaleStartedAt",
        "scaleCompletedAt",
        "wallClockBudgetSeconds",
        "wallClockSeconds",
        "resourceSoakEvidenceRef",
        "resourceSoakEvidenceDigest",
        "faultInjectionEvidenceRef",
        "faultInjectionEvidenceDigest",
    }
    promotion_diagnostics = {
        "scaleStartedAt",
        "scaleCompletedAt",
        "wallClockBudgetSeconds",
        "wallClockSeconds",
        "capacityThroughputByCarrier",
        "resourceIsolationPassed",
        "soakDurationSeconds",
        "semanticJobsByLane",
        "fourLaneOverlapSampleCount",
        "fourLaneOverlapDurationSeconds",
        "fourLaneLongestContinuousOverlapSeconds",
        "allSemanticJobsTerminalAt",
        "terminalResidualSampleAt",
        "resourceSoakEvidenceRef",
        "resourceSoakEvidenceDigest",
        "faultInjectionEvidenceRef",
        "faultInjectionEvidenceDigest",
    }

    assert campaign_diagnostics.isdisjoint(campaign_schema["required"])
    assert promotion_diagnostics.isdisjoint(promotion_schema["required"])
    assert loader_parameter.default is False
    assert {
        "automaticRecoveryRate",
        "capacityPlanning",
        "resourceSoak",
    }.isdisjoint(promotion_schema["$defs"]["statistics"]["required"])
    campaign_m10000 = campaign_schema["allOf"][3]["then"]["properties"]
    promotion_m10000 = promotion_schema["allOf"][3]["then"]["properties"]
    assert "wallClockBudgetSeconds" not in campaign_m10000
    assert "wallClockBudgetSeconds" not in promotion_m10000
    assert "maximum" not in promotion_m10000.get("wallClockSeconds", {})
    for milestone_index in (1, 2):
        carrier_rules = promotion_schema["allOf"][milestone_index]["then"][
            "properties"
        ]["carrierCounts"]["prefixItems"]
        for rule in carrier_rules:
            count_rules = rule["properties"]
            assert "minimum" in count_rules["totalUniqueFinalizedCount"]
            assert "minimum" in count_rules["researchAcceptedCount"]


def test_campaign_runtime_diagnostic_failure_is_recorded_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_fields = {
        "runtimeSessionId": "session-001",
        "runtimeSessionRef": "data/runtime/session.json",
        "runtimeSessionDigest": "sha256:" + "1" * 64,
        "runId": "run-001",
        "generation": 1,
        "fencingToken": "sha256:" + "2" * 64,
    }
    monkeypatch.setattr(
        campaign_scale_diagnostics_module.runtime_binding,
        "materialize_bound_runtime_inputs",
        lambda **_kwargs: (
            {"runtime": "session"},
            tmp_path / "samples.json",
            tmp_path / "faults.json",
        ),
    )
    monkeypatch.setattr(
        campaign_scale_diagnostics_module.runtime_binding,
        "runtime_binding_fields",
        lambda *_args, **_kwargs: runtime_fields,
    )

    def unavailable(**_kwargs: object) -> None:
        raise CampaignScaleEvidenceError("diagnostic input unavailable")

    monkeypatch.setattr(
        campaign_scale_diagnostics_module,
        "write_resource_soak_evidence",
        unavailable,
    )
    monkeypatch.setattr(
        campaign_scale_diagnostics_module,
        "write_fault_injection_evidence",
        unavailable,
    )

    fields = campaign_scale_diagnostics_module.derive_runtime_diagnostic_fields(
        evidence_id="evidence-001",
        runtime_session_path=tmp_path / "runtime-session.json",
        campaign_plan_path=tmp_path / "campaign-plan.json",
        tasks_root=tmp_path / "tasks",
        release=tmp_path / "release",
        output_root=tmp_path,
        evidence_root=tmp_path / "evidence",
        target_scale="M10000",
        predecessor_promotion_path=tmp_path / "predecessor.json",
    )

    assert {key: fields[key] for key in runtime_fields} == runtime_fields
    assert "status" not in fields
    assert "resourceSoakEvidenceRef" not in fields
    assert "faultInjectionEvidenceRef" not in fields
    assert any("RESOURCE_SOAK_UNAVAILABLE" in issue for issue in fields["diagnosticIssues"])
    assert any("FAULT_INJECTION_UNAVAILABLE" in issue for issue in fields["diagnosticIssues"])


def test_cumulative_scale_context_binds_predecessor_and_current_execution_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    release_root = output / "data/releases"
    predecessor_release = release_root / "predecessor-release"
    source_revision = _digest(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
        }
    )
    predecessor_ids = {carrier: _execution_id(carrier) for carrier in CARRIERS}
    current_ids = {
        carrier: _execution_id(carrier).replace("-m100--", "-m1000--")
        for carrier in CARRIERS
    }
    predecessor_header = {
        "schema": "quwoquan_data.release",
        "releaseId": "predecessor-release",
        "sourceOwner": "qwq_data",
        "releaseKind": "content",
        "releaseClass": "research",
        "productLifecycleState": "research",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 0,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 4,
        "commercialAcceptedCount": 0,
        "canonicalMerkle": "sha256:" + "e" * 64,
        "executionIds": list(predecessor_ids.values()),
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "sourceDigests": [SOURCE_DIGEST_DOCUMENT],
    }
    _write(predecessor_release / "payload/release.json", predecessor_header)
    _write(
        predecessor_release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": "predecessor-release",
            "desiredRefs": {
                "entities": ["地点/景区/predecessor"],
                "posts": [
                    "article/predecessor/001",
                    "image/predecessor/001",
                    "video/predecessor/001",
                ],
                "creators": [],
                "tags": [],
            },
        },
    )
    manifest_digest = campaign_scale_cumulative.payload_digest(predecessor_release)
    predecessor_reference = {
        "promotionId": "promotion-m100",
        "releaseId": "predecessor-release",
        "manifestDigest": manifest_digest,
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "targetScale": "M100",
        "receiptRef": "data/local/workspace/promotions/promotion-m100.json",
        "receiptDigest": "sha256:" + "c" * 64,
    }
    monkeypatch.setattr(
        campaign_scale_cumulative,
        "load_predecessor_promotion",
        lambda *_args, **_kwargs: (
            predecessor_reference,
            {carrier: 1 for carrier in CARRIERS},
        ),
    )
    plan = {
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "executionIds": current_ids,
    }
    current_header = {
        **predecessor_header,
        "releaseId": "current-release",
        "executionIds": [*predecessor_ids.values(), *current_ids.values()],
    }

    scale, predecessor, counts, carried_ids, release_ids, refs = (
        campaign_scale_cumulative.scale_context(
            target_scale="M1000",
            predecessor_promotion_path=output / predecessor_reference["receiptRef"],
            plan=plan,
            header=current_header,
            release_root=release_root,
            output_root=output,
        )
    )

    assert scale == "M1000"
    assert predecessor == predecessor_reference
    assert counts == {carrier: 1 for carrier in CARRIERS}
    assert carried_ids == sorted(predecessor_ids.values())
    assert release_ids == sorted(current_header["executionIds"])
    assert {carrier: len(refs[carrier]) for carrier in CARRIERS} == {
        carrier: 1 for carrier in CARRIERS
    }

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="release executionIds must preserve the predecessor milestone cohort",
    ):
        campaign_scale_cumulative.scale_context(
            target_scale="M1000",
            predecessor_promotion_path=output / predecessor_reference["receiptRef"],
            plan=plan,
            header={**current_header, "executionIds": list(current_ids.values())},
            release_root=release_root,
            output_root=output,
        )


def test_campaign_scale_evidence_records_m100_as_zero_carried_cumulative_baseline(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    evidence, path = _write_evidence(fixture)

    loaded, _resource, _fault = load_campaign_scale_evidence(
        path,
        output_root=fixture["output"],
    )
    assert loaded == evidence
    assert evidence["targetScale"] == "M100"
    assert evidence["predecessorCarriedExecutionIds"] == []
    assert evidence["releaseExecutionIds"] == sorted(
        fixture["plan"]["executionIds"].values()
    )
    assert [row["predecessorCarriedCount"] for row in evidence["lanes"]] == [0] * 4
    assert [row["newFinalizedCount"] for row in evidence["lanes"]] == [100] * 4
    assert [row["totalUniqueFinalizedCount"] for row in evidence["lanes"]] == [
        100,
        100,
        100,
        10,
    ]
    assert evidence["scaleStartedAt"] == START.isoformat()
    assert evidence["scaleCompletedAt"] == (
        START + timedelta(hours=1, minutes=2)
    ).isoformat()
    assert evidence["wallClockBudgetSeconds"] is None
    assert evidence["wallClockSeconds"] == 3720


def test_campaign_scale_source_pool_blocks_predecessor_candidate_reuse(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    evidence, evidence_path = _write_evidence(fixture)
    promotion, promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-source-pool-lineage",
        campaign_evidence_path=evidence_path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )
    release_header = json.loads(
        (
            fixture["releaseRoot"]
            / "research-release/payload/release.json"
        ).read_text(encoding="utf-8")
    )
    assert promotion["sourcePoolDigest"] == release_header["poolDigest"]
    assert promotion["campaignSourcePoolDigest"] == evidence["sourcePoolDigest"]
    assert evidence["predecessorSourcePoolDigests"] == []

    current_pool = json.loads(json.dumps(evidence["sourcePool"]))
    current_pool["poolId"] = "research-m1000-pool-001"
    current_pool["targetScale"] = "M1000"
    with pytest.raises(CampaignScaleEvidenceError, match="POOL_SHORTFALL.*reused"):
        source_pool_lineage_fields(
            source_pool_fields={
                "sourcePool": current_pool,
                "sourcePoolDigest": _digest(current_pool),
            },
            target_scale="M1000",
            predecessor_promotion_path=promotion_path,
            output_root=fixture["output"],
        )


def test_cumulative_scale_wall_clock_preserves_budget_as_nonblocking_diagnostic(
    tmp_path: Path,
) -> None:
    predecessor_path = tmp_path / "predecessor-promotion.json"
    _write(predecessor_path, {"recordedAt": START.isoformat()})
    plan = {"frozenAt": (START - timedelta(days=30)).isoformat()}

    at_budget = campaign_scale_cumulative.scale_timing_fields(
        target_scale="M1000",
        plan=plan,
        predecessor_promotion_path=predecessor_path,
        resource={
            "allSemanticJobsTerminalAt": (START + timedelta(days=2)).isoformat(),
            "terminalResidualSampleAt": (START + timedelta(days=3)).isoformat(),
        },
    )

    assert at_budget == {
        "scaleStartedAt": START.isoformat(),
        "scaleCompletedAt": (START + timedelta(days=3)).isoformat(),
        "wallClockBudgetSeconds": None,
        "wallClockSeconds": 259200,
    }
    m1000_exceeded = campaign_scale_cumulative.scale_timing_fields(
        target_scale="M1000",
        plan=plan,
        predecessor_promotion_path=predecessor_path,
        resource={
            "terminalResidualSampleAt": (
                START + timedelta(seconds=259201)
            ).isoformat()
        },
    )
    assert m1000_exceeded["wallClockBudgetSeconds"] is None
    assert m1000_exceeded["wallClockSeconds"] == 259201

    m10000_exceeded = campaign_scale_cumulative.scale_timing_fields(
        target_scale="M10000",
        plan=plan,
        predecessor_promotion_path=predecessor_path,
        resource={
            "terminalResidualSampleAt": (
                START + timedelta(seconds=604801)
            ).isoformat()
        },
    )
    assert m10000_exceeded["wallClockBudgetSeconds"] == 604800
    assert m10000_exceeded["wallClockSeconds"] == 604801


def test_promotion_timing_revalidates_projection_without_enforcing_budget() -> None:
    m1000_completed = START + timedelta(seconds=259200)
    evidence = {
        "targetScale": "M1000",
        "scaleStartedAt": START.isoformat(),
        "scaleCompletedAt": m1000_completed.isoformat(),
        "wallClockBudgetSeconds": None,
        "wallClockSeconds": 259200,
    }

    assert validate_promotion_timing(
        target_scale="M1000",
        evidence=evidence,
        resource_evidence={"terminalResidualSampleAt": m1000_completed.isoformat()},
    ) == {
        "scaleStartedAt": START.isoformat(),
        "scaleCompletedAt": m1000_completed.isoformat(),
        "wallClockBudgetSeconds": None,
        "wallClockSeconds": 259200,
    }

    exceeded = START + timedelta(seconds=259201)
    assert validate_promotion_timing(
        target_scale="M1000",
        evidence={
            **evidence,
            "scaleCompletedAt": exceeded.isoformat(),
            "wallClockSeconds": 259201,
        },
        resource_evidence={"terminalResidualSampleAt": exceeded.isoformat()},
    )["wallClockSeconds"] == 259201

    m10000_exceeded = START + timedelta(seconds=604801)
    assert validate_promotion_timing(
        target_scale="M10000",
        evidence={
            **evidence,
            "targetScale": "M10000",
            "scaleCompletedAt": m10000_exceeded.isoformat(),
            "wallClockBudgetSeconds": 604800,
            "wallClockSeconds": 604801,
        },
        resource_evidence={
            "terminalResidualSampleAt": m10000_exceeded.isoformat()
        },
    )["wallClockSeconds"] == 604801


def test_promotion_writer_records_timing_failure_without_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)

    def block_timing(**_kwargs: object) -> dict[str, object]:
        raise ResearchScalePromotionTimingError(
            "DATA.SCALE.M10000_WALL_CLOCK_BUDGET_EXCEEDED: governed timing blocker"
        )

    monkeypatch.setattr(
        promotion_diagnostics_module,
        "validate_promotion_timing",
        block_timing,
    )
    promotion, _promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-wall-clock-diagnostic",
        campaign_evidence_path=path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )

    assert "scaleStartedAt" not in promotion
    assert any(
        "M10000_WALL_CLOCK_BUDGET_EXCEEDED" in issue
        for issue in promotion["diagnosticIssues"]
    )


def test_m100_promotion_reports_unranked_video_without_blocking(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    release = fixture["releaseRoot"] / "research-release"
    rights_path = next((release / "payload/objects/posts/video").rglob("rights.json"))
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    receipt_ref = rights["assets"][0]["independentAssetReview"]["receiptRef"]
    receipt_path = fixture["output"] / receipt_ref
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    signals = receipt["assetSnapshot"]["popularitySignals"]
    signals.update(
        {
            "favoriteCount": None,
            "popularityScore": None,
            "popularityPercentile": None,
            "rankingEligible": False,
            "ineligibleReason": "incomplete_popularity_signals",
        }
    )
    receipt["receiptDigest"] = _digest(
        {key: value for key, value in receipt.items() if key != "receiptDigest"}
    )
    _write(receipt_path, receipt)
    rights["assets"][0]["independentAssetReview"].update(
        {
            "receiptDigest": receipt["receiptDigest"],
            "receiptFileSha256": _file_digest(receipt_path),
            "popularitySignalsDigest": _digest(signals),
        }
    )
    _write(rights_path, rights)
    _evidence, path = _write_evidence(fixture)

    promotion, _promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-unranked-video",
        campaign_evidence_path=path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )

    statistic = promotion["statistics"]["videoPopularity"]
    assert statistic["nonBlocking"] is True
    assert statistic["rankingCoverage"]["rate"] < 1
    favorite = next(
        row for row in statistic["signalAvailability"]
        if row["signal"] == "favorite"
    )
    assert favorite["rate"] < 1
