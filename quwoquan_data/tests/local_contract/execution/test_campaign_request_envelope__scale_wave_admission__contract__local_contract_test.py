"""Generic campaign request envelopes freeze once and validate schema."""

from __future__ import annotations

from pathlib import Path

import content.execution.campaign.request_envelope as envelopes
import pytest
from content.release.canonical.research_scale_capacity import throughput_basis_digest
from content.release.canonical.research_scale_promotion_acceptance import (
    acceptance_binding_fields,
)
from core.io import read_json, write_json
from core.paths import research_scale_promotions_root
from support.m100_alpha_acceptance_fixture import unproven_acceptance_binding
from support.campaign_request_envelope_fixture import (
    _expected_count,
    _patch_envelope_deps,
    _pool_kwargs,
    _promotion_output_root,
    _research_m100_receipt,
    _wave_targets,
)


def _research_m1000_receipt(path: Path) -> Path:
    m100 = _research_m100_receipt(path)
    document = read_json(m100)
    document.update(
        {
            "promotionId": "research-m1000-1",
            "releaseId": "research-release-m1000-1",
            "targetScale": "M1000",
            "sourcePoolDigest": "sha256:" + "5" * 64,
            "predecessorSourcePoolDigests": ["sha256:" + "4" * 64],
            "scaleStartedAt": "2026-08-05T00:00:00Z",
            "scaleCompletedAt": "2026-08-08T00:00:00Z",
            "wallClockBudgetSeconds": None,
            "wallClockSeconds": 259200,
            "nextScaleEligible": "M10000",
            "campaignEvidenceRef": "data/local/campaign/m1000-evidence.json",
            "campaignEvidenceDigest": "sha256:" + "6" * 64,
            "predecessorPromotion": {
                "promotionId": "research-m100-1",
                "releaseId": "research-release-1",
                "manifestDigest": "sha256:" + "c" * 64,
                "sourceRevision": document["sourceRevision"],
                "sourceDigest": document["sourceDigest"],
                "entityCatalogDigest": document["entityCatalogDigest"],
                "targetScale": "M100",
                "receiptRef": "data/promotions/research-m100.json",
                "receiptDigest": "sha256:" + "9" * 64,
            },
        }
    )
    for row in document["carrierCounts"]:
        target = 100 if row["carrier"] == "video" else 1000
        carried = 10 if row["carrier"] == "video" else 100
        delta = target - carried
        row.update(
            {
                "targetCount": target,
                "qualifiedCount": delta,
                "finalizedCount": delta,
                "predecessorCarriedCount": carried,
                "newFinalizedCount": delta,
                "totalUniqueFinalizedCount": target,
                "selectedCount": delta,
                "researchAcceptedCount": target,
            }
        )
    document["statistics"]["automaticRecoveryRate"].update(
        {"eligibleCount": 50, "automaticCount": 48, "rate": 0.96}
    )
    for row in document["capacityThroughputByCarrier"]:
        row["measuredScale"] = "M1000"
        row["throughputBasisDigest"] = throughput_basis_digest(row)
    document["statistics"]["quotaAttainmentByCarrier"] = [
        {
            "carrier": carrier,
            "numerator": 100 if carrier == "video" else 1000,
            "denominator": 100 if carrier == "video" else 1000,
            "rate": 1.0,
        }
        for carrier in ("homepage", "article", "image", "video")
    ]
    document["professionalImageSourceMix"].update(
        {
            "acceptedImageAssetCount": 1000,
            "originalAssetClosureCount": 1000,
            "pinterestAcceptedAssetCount": 600,
            "tuchongAcceptedAssetCount": 200,
            "pinterestTuchongAcceptedAssetCount": 800,
        }
    )
    document["professionalImageSourceMix"]["providerAssetCounts"] = [
        {
            "provider": row["provider"],
            "acceptedAssetCount": row["acceptedAssetCount"] * 10,
            "acceptedAssetRatio": row["acceptedAssetRatio"],
        }
        for row in document["professionalImageSourceMix"]["providerAssetCounts"]
    ]
    # M1000 promotion 的 schema 要求携带 M100 alpha 验收绑定。本用例只消费 M1000
    # 的规模谱系与承载计数；验收证据本身由 release 域的 acceptance 用例校验，所以
    # 这里只需要一份形状完整的绑定。
    acceptance = unproven_acceptance_binding(
        promotion_receipt_ref="data/promotions/research-m100.json",
        readiness_receipt_ref="data/releases/research-release-1/readiness.json",
        app_uat_receipt_ref="data/releases/research-release-1/app-uat.json",
    )
    document.update(acceptance_binding_fields(acceptance, {}))
    m1000_path = (
        research_scale_promotions_root(output_root=path)
        / "research-release-m1000-1"
        / "research-m1000-1"
        / "research-m1000.json"
    )
    write_json(m1000_path, document)
    return m1000_path


def test_travel_video_m1000_dispatch_does_not_require_predecessor_or_alpha(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    envelope = envelopes.build_envelope(
        scale="M1000",
        carrier="video",
        region_ref="china",
        repo_root=repo,
        day="20260731",
    )
    assert envelope["quota"] == 1000
    assert envelope["count"] == _expected_count(1000)
    assert "researchScalePromotion" not in envelope
    assert "m100AlphaAcceptance" not in envelope


def test_execution_wire_schemas_forbid_alpha_m100_acceptance() -> None:
    repo = Path(__file__).resolve().parents[4]
    schema_root = repo / "quwoquan_data/schema/execution"
    for name in (
        "content_campaign_request_envelope.schema.json",
        "content_execution_submission.schema.json",
        "content_campaign_plan.schema.json",
    ):
        schema = read_json(schema_root / name)
        assert "m100AlphaAcceptance" not in schema["properties"]
        assert "m100AlphaAcceptance" not in (schema_root / name).read_text()


def test_m100_and_m1000_are_create_once_current_waves_without_campaign_wide_pool_or_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    m100 = envelopes.write_scale_envelopes(
        "M100",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path / "m100-wave",
        day="20260811",
        target_names=_wave_targets("m100"),
    )
    m100_targets = {"homepage": 100, "article": 100, "image": 100, "video": 10}
    for carrier, path in m100.items():
        payload = read_json(path)
        assert "scaleSourcePool" not in payload
        assert payload["workerHostSetBinding"] is None
        assert payload["quota"] == m100_targets[carrier]

    common = {
        "region_ref": "china",
        "repo_root": repo,
        "day": "20260811",
    }
    first = envelopes.write_scale_envelopes(
        "M1000",
        output_root=tmp_path / "m1000-waves",
        sequence=1,
        target_names=_wave_targets("first"),
        **common,
    )
    second = envelopes.write_scale_envelopes(
        "M1000",
        output_root=tmp_path / "m1000-waves",
        sequence=2,
        target_names=_wave_targets("second"),
        **common,
    )

    m1000_targets = {"homepage": 1000, "article": 1000, "image": 1000, "video": 100}
    for carrier in ("homepage", "article", "image", "video"):
        first_payload = read_json(first[carrier])
        second_payload = read_json(second[carrier])
        assert first_payload["workerHostSetBinding"] is None
        assert second_payload["workerHostSetBinding"] is None
        assert "scaleSourcePool" not in first_payload
        assert "scaleSourcePool" not in second_payload
        assert (
            first_payload["quota"]
            == second_payload["quota"]
            == m1000_targets[carrier]
        )
        # DEC-002：capacityPlanDigest 只在 execution freeze 落地，信封只保证两个
        # wave 是同一份 calibration receipt admitted 出来的。
        assert "capacityPlanDigest" not in first_payload
        assert (
            first_payload["capacityCalibration"]
            == second_payload["capacityCalibration"]
        )
        assert first_payload["executionId"] != second_payload["executionId"]
        assert first_payload["requestDigest"] != second_payload["requestDigest"]
        assert "wallClockBudgetSeconds" not in second_payload
        assert second_payload["retryOf"] is None

    envelopes.load_campaign_envelope(first["homepage"])


def test_selected_carriers_get_independent_workload_plans_without_host_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    paths = envelopes.write_scale_envelopes(
        "M100",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path / "selected",
        day="20260811",
        target_names=_wave_targets("selected"),
        carriers=("homepage", "video"),
        workloads={"homepage": 12, "video": 12},
    )
    payloads = {carrier: read_json(path) for carrier, path in paths.items()}
    assert set(payloads) == {"homepage", "video"}
    for payload in payloads.values():
        assert payload["workerHostSetBinding"] is None
        # DEC-002：并发上限与分区数由 execution freeze 从 calibration receipt 推导，
        # 信封只携带被 admit 的 calibration 来源。
        assert "requiredWorkers" not in payload
        assert "partitionCount" not in payload
        assert payload["capacityCalibration"]["calibrationReceiptDigest"]


def test_travel_image_m1000_dispatch_does_not_require_predecessor_or_alpha(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    envelope = envelopes.build_envelope(
        scale="M1000",
        carrier="image",
        region_ref="china",
        repo_root=repo,
        day="20260731",
    )

    assert envelope["count"] == _expected_count(1000)
    assert envelope["quota"] == 1000
    assert "researchScalePromotion" not in envelope
    assert "m100AlphaAcceptance" not in envelope


def test_m10000_consumes_m1000_cumulative_counts_as_delta(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    approved = _research_m1000_receipt(tmp_path / "m1000.json")
    milestone_workloads = {
        "homepage": 10000,
        "article": 10000,
        "image": 10000,
        "video": 1000,
    }
    homepage = envelopes.build_envelope(
        scale="M10000",
        carrier="homepage",
        region_ref="china",
        repo_root=repo,
        day="20260731",
        promotion_receipt=approved,
        promotion_output_root=_promotion_output_root(approved),
        active_carriers=("homepage", "article", "image", "video"),
        workloads=milestone_workloads,
        workload_mode="milestone_preset",
        **_pool_kwargs(tmp_path),
    )
    video = envelopes.build_envelope(
        scale="M10000",
        carrier="video",
        region_ref="china",
        repo_root=repo,
        day="20260731",
        promotion_receipt=approved,
        promotion_output_root=_promotion_output_root(approved),
        active_carriers=("homepage", "article", "image", "video"),
        workloads=milestone_workloads,
        workload_mode="milestone_preset",
        **_pool_kwargs(tmp_path),
    )

    assert homepage["quota"] == 9000
    assert homepage["count"] == _expected_count(9000)
    assert video["quota"] == 900
    assert video["count"] == _expected_count(900)
    assert homepage["researchScalePromotion"]["targetScale"] == "M1000"
    assert homepage["researchScalePromotion"]["carrierCounts"][0] == {
        "carrier": "homepage",
        "totalUniqueFinalizedCount": 1000,
    }
