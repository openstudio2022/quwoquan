"""Generic campaign request envelopes freeze once and validate schema."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import content.execution.campaign.request_envelope as envelopes
import pytest
from content.execution.campaign import request_envelope_writer
from content.execution.campaign.external_inputs import content_source_revision
from content.execution.preflight.receipt import _digest as semantic_preflight_digest
from content.execution.scale.capacity_plan import throughput_basis_digest
from content.execution.scale.host_set import build_governed_host_set
from content.execution.scale.source_capsule import (
    build_governed_host_source_capsule,
)
from core.io import read_json, write_json
from core.paths import research_scale_promotions_root
from support.campaign_request_envelope_fixture import (
    _expected_count,
    _patch_envelope_deps,
    _pool_kwargs,
    _promotion_output_root,
    _research_m100_receipt,
    _wave_targets,
)
from support.semantic_preflight_fixture import ready_semantic_preflight


def _document_digest(document: dict[str, object]) -> str:
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _alpha_acceptance_kwargs(
    root: Path, promotion_path: Path
) -> dict[str, Path]:
    promotion = read_json(promotion_path)
    evidence_root = root / "alpha-m100-acceptance"
    readiness_path = evidence_root / "release-readiness.json"
    app_uat_path = evidence_root / "app-uat.json"
    post_ids = [f"post-{index:03d}" for index in range(210)]
    entity_refs = [f"homepage-{index:03d}" for index in range(100)]
    app_envelope = {"releaseId": promotion["releaseId"], "sample": "m100"}
    app_envelope_digest = _document_digest(app_envelope)
    activation = {
        "environment": "alpha",
        "releaseId": promotion["releaseId"],
        "manifestDigest": promotion["manifestDigest"],
        "releaseClass": "research",
        "productLifecycleState": "research",
        "readinessPhase": "research",
        "appUatEnvelopeDigest": app_envelope_digest,
    }
    readiness: dict[str, object] = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": "alpha",
        "releaseId": promotion["releaseId"],
        "manifestDigest": promotion["manifestDigest"],
        "releaseClass": "research",
        "productLifecycleState": "research",
        "readinessPhase": "research",
        "passed": True,
        "counts": {
            "entities": 100,
            "posts": 210,
            "premiumPlayableVideos": 10,
        },
        "entityRefs": entity_refs,
        "postIds": post_ids,
        "activationEnvelope": activation,
        "activationEnvelopeDigest": _document_digest(activation),
        "appUatEnvelope": app_envelope,
        "appUatEnvelopeDigest": app_envelope_digest,
    }
    readiness["verificationChecksum"] = _document_digest(readiness)
    write_json(readiness_path, readiness)
    readiness_digest = _document_digest(readiness)
    app_plan = {"releaseId": promotion["releaseId"], "sample": "alpha-m100"}
    app_uat = {
        "schema": "quwoquan_ops.app_content_uat_receipt",
        "status": "passed",
        "targets": ["alpha-local"],
        "releaseId": promotion["releaseId"],
        "manifestDigest": promotion["manifestDigest"],
        "appUatEnvelopeDigest": app_envelope_digest,
        "readinessReceiptDigests": [readiness_digest],
        "appUatPlan": app_plan,
        "appUatPlanDigest": _document_digest(app_plan),
        "preflights": [
            {
                "target": "alpha-local",
                "environment": "alpha",
                "status": "passed",
                "exitCode": 0,
                "launchPolicy": "test_live",
                "contentBindingState": "bound",
                "releaseId": promotion["releaseId"],
                "manifestDigest": promotion["manifestDigest"],
                "readinessReceiptDigest": readiness_digest,
                "appUatEnvelope": app_envelope,
                "appUatPlan": app_plan,
                "appUatPlanDigest": _document_digest(app_plan),
            }
        ],
        "runtimeBindings": {
            "alpha-local": {
                "environment": "alpha",
                "contentBindingState": "bound",
                "releaseId": promotion["releaseId"],
                "manifestDigest": promotion["manifestDigest"],
                "readinessPhase": "research",
            }
        },
        "runs": [{"target": "alpha-local", "suite": "app-core-readback", "exitCode": 0}],
        "executed": 1,
        "skipped": 0,
    }
    write_json(app_uat_path, app_uat)
    return {
        "alpha_m100_readiness_receipt": readiness_path,
        "alpha_m100_app_uat_receipt": app_uat_path,
        "alpha_m100_acceptance_output_root": root,
    }


def _capacity_host_set(tmp_path: Path) -> Path:
    source_digest = "sha256:" + "a" * 64
    catalog_digest = "sha256:" + "b" * 64
    capsule = build_governed_host_source_capsule(
        capsule_id="request-envelope-source-capsule",
        source_revision=content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=catalog_digest,
        ),
        source_digest={
            "algorithm": "sha256",
            "digest": source_digest,
            "inputs": ["quwoquan_data/scripts"],
        },
        entity_catalog_digest=catalog_digest,
        executor_bundle_ref="data/executor/content-worker",
        executor_bundle_digest="sha256:" + "c" * 64,
        executor_bundle_file_sha256="sha256:" + "d" * 64,
    )
    hosts = []
    for host_id in ("worker-alpha", "worker-beta"):
        receipt_path, _binding = ready_semantic_preflight(
            "cursor_auto",
            output_root=tmp_path / host_id,
            effective_concurrency=4,
        )
        receipt = read_json(receipt_path)
        receipt["evidence"]["workspaceSmoke"]["runs"] = [
            {"lane": "homepage", "workspace": host_id, "status": "FINISHED"}
        ]
        receipt["evidenceDigest"] = semantic_preflight_digest(receipt["evidence"])
        receipt["receiptId"] = semantic_preflight_digest({
            key: value for key, value in receipt.items() if key != "receiptId"
        })
        hosts.append({
            "hostScopeId": host_id,
            "preflightReceipt": receipt,
            "sourceCapsule": capsule,
            "mongoTransportDigest": "sha256:" + "8" * 64,
            "redisTransportDigest": "sha256:" + "9" * 64,
        })
    document = build_governed_host_set(
        host_set_id="request-envelope-workers",
        source_revision=content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=catalog_digest,
        ),
        source_digest=source_digest,
        entity_catalog_digest=catalog_digest,
        hosts=hosts,
    )
    path = tmp_path / "governed-host-set.json"
    write_json(path, document)
    return path


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
    m1000_path = (
        research_scale_promotions_root(output_root=path)
        / "research-release-m1000-1"
        / "research-m1000-1"
        / "research-m1000.json"
    )
    write_json(m1000_path, document)
    return m1000_path


def test_travel_video_m1000_requires_promotion_and_alpha_acceptance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    with pytest.raises(ValueError, match="M1000 requires M100 promotion"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="video",
            region_ref="china",
            repo_root=repo,
            day="20260731",
        )

    approved = _research_m100_receipt(tmp_path / "m100.json")
    with pytest.raises(ValueError, match="ALPHA_M100_ACCEPTANCE_MISSING"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="video",
            region_ref="china",
            repo_root=repo,
            day="20260731",
            promotion_receipt=approved,
            promotion_output_root=_promotion_output_root(approved),
        )
    preflight_root = _promotion_output_root(approved)
    preflight_path, _binding = ready_semantic_preflight(
        "cursor_auto", output_root=preflight_root, effective_concurrency=8
    )
    alpha_acceptance = _alpha_acceptance_kwargs(preflight_root, approved)
    with pytest.raises(ValueError, match="ALPHA_M100_ACCEPTANCE_MISSING"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="video",
            region_ref="china",
            repo_root=repo,
            day="20260731",
            promotion_receipt=approved,
            promotion_output_root=_promotion_output_root(approved),
            alpha_m100_readiness_receipt=alpha_acceptance[
                "alpha_m100_readiness_receipt"
            ],
        )
    envelope = envelopes.build_envelope(
        scale="M1000",
        carrier="video",
        region_ref="china",
        repo_root=repo,
        day="20260731",
        promotion_receipt=approved,
        promotion_output_root=_promotion_output_root(approved),
        semantic_selection_id="cursor_auto",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=preflight_root,
        capacity_host_set=_capacity_host_set(tmp_path / "capacity-hosts"),
        target_names=_wave_targets("video"),
        **alpha_acceptance,
        **_pool_kwargs(tmp_path),
    )
    assert envelope["quota"] == 12
    assert envelope["count"] == _expected_count(12)
    assert envelope["researchScalePromotion"]["promotionId"] == "research-m100-1"


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
    for path in m100.values():
        payload = read_json(path)
        assert "scaleSourcePool" not in payload
        assert payload["workerHostSetBinding"] is None
        assert payload["quota"] <= 12

    promotion = _research_m100_receipt(tmp_path / "promotion")
    preflight_root = _promotion_output_root(promotion)
    preflight, _binding = ready_semantic_preflight(
        "cursor_auto", output_root=preflight_root, effective_concurrency=8
    )
    common = {
        "region_ref": "china",
        "repo_root": repo,
        "day": "20260811",
        "promotion_receipt": promotion,
        "promotion_output_root": _promotion_output_root(promotion),
        "semantic_selection_id": "cursor_auto",
        "semantic_preflight_receipt": preflight,
        "semantic_preflight_output_root": preflight_root,
        **_alpha_acceptance_kwargs(preflight_root, promotion),
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

    for carrier in ("homepage", "article", "image", "video"):
        first_payload = read_json(first[carrier])
        second_payload = read_json(second[carrier])
        assert first_payload["workerHostSetBinding"] is None
        assert second_payload["workerHostSetBinding"] is None
        assert "scaleSourcePool" not in first_payload
        assert "scaleSourcePool" not in second_payload
        assert first_payload["quota"] == second_payload["quota"] == 12
        assert first_payload["capacityPlanDigest"] == second_payload["capacityPlanDigest"]
        assert first_payload["executionId"] != second_payload["executionId"]
        assert first_payload["requestDigest"] != second_payload["requestDigest"]
        assert "wallClockBudgetSeconds" not in second_payload
        assert second_payload["retryOf"] is None

    envelopes.load_campaign_envelope(
        first["homepage"], semantic_preflight_output_root=preflight_root
    )
    app_uat_path = common["alpha_m100_app_uat_receipt"]
    app_uat = read_json(app_uat_path)
    app_uat["status"] = "gate_block"
    write_json(app_uat_path, app_uat)
    with pytest.raises(ValueError, match="APP_UAT_DRIFT"):
        envelopes.load_campaign_envelope(
            first["homepage"], semantic_preflight_output_root=preflight_root
        )


def test_explicit_m1000_host_set_remains_cross_lane_identity_strict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    promotion = _research_m100_receipt(tmp_path / "promotion")
    preflight_root = _promotion_output_root(promotion)
    preflight, _binding = ready_semantic_preflight(
        "cursor_auto", output_root=preflight_root, effective_concurrency=8
    )
    paths = envelopes.write_scale_envelopes(
        "M1000",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path / "governed",
        day="20260811",
        target_names=_wave_targets("governed"),
        promotion_receipt=promotion,
        promotion_output_root=_promotion_output_root(promotion),
        semantic_selection_id="cursor_auto",
        semantic_preflight_receipt=preflight,
        semantic_preflight_output_root=preflight_root,
        capacity_host_set=_capacity_host_set(tmp_path / "capacity-hosts"),
        **_alpha_acceptance_kwargs(preflight_root, promotion),
    )
    payloads = {carrier: read_json(path) for carrier, path in paths.items()}
    payloads["video"]["workerHostSetBinding"]["hostSetDigest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="host-set identity changed"):
        request_envelope_writer._assert_one_capacity_plan(payloads)


def test_travel_image_m1000_requires_promotion_and_alpha_acceptance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    with pytest.raises(ValueError, match="M1000 requires M100 promotion"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260731",
        )

    approved = _research_m100_receipt(tmp_path / "m100.json")
    preflight_root = _promotion_output_root(approved)
    preflight_path, _binding = ready_semantic_preflight(
        "cursor_auto", output_root=preflight_root
    )
    envelope = envelopes.build_envelope(
        scale="M1000",
        carrier="image",
        region_ref="china",
        repo_root=repo,
        day="20260731",
        promotion_receipt=approved,
        promotion_output_root=_promotion_output_root(approved),
        semantic_selection_id="cursor_auto",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=preflight_root,
        capacity_host_set=_capacity_host_set(tmp_path / "capacity-hosts"),
        target_names=_wave_targets("image"),
        **_alpha_acceptance_kwargs(preflight_root, approved),
        **_pool_kwargs(tmp_path),
    )

    assert envelope["count"] == _expected_count(12)
    assert envelope["quota"] == 12
    assert envelope["researchScalePromotion"]["releaseId"] == "research-release-1"


def test_m10000_consumes_m1000_cumulative_counts_as_delta(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    approved = _research_m1000_receipt(tmp_path / "m1000.json")
    preflight_root = tmp_path / "semantic-output"
    preflight_path, _binding = ready_semantic_preflight(
        "cursor_auto", output_root=preflight_root, effective_concurrency=8
    )

    homepage = envelopes.build_envelope(
        scale="M10000",
        carrier="homepage",
        region_ref="china",
        repo_root=repo,
        day="20260731",
        promotion_receipt=approved,
        promotion_output_root=_promotion_output_root(approved),
        semantic_selection_id="cursor_auto",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=preflight_root,
        capacity_host_set=_capacity_host_set(tmp_path / "capacity-hosts"),
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
        semantic_selection_id="cursor_auto",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=preflight_root,
        capacity_host_set=_capacity_host_set(tmp_path / "capacity-hosts"),
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
