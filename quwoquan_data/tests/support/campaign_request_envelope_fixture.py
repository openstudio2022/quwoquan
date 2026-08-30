"""Generic campaign request envelopes freeze once and validate schema."""

from __future__ import annotations

import math
from pathlib import Path

import content.execution.campaign.request_envelope as envelopes
from content.execution.campaign import (
    m100_alpha_acceptance,
    request_envelope_build,
    request_envelope_writer,
)
from content.execution.campaign.external_inputs import content_source_revision
from content.execution.campaign.scale import resolve_campaign_scale
from core.source_digest import SourceDefinitionSnapshot
from content.release.canonical.research_scale_capacity import throughput_basis_digest
from core.io import write_json
from core.paths import research_scale_promotions_root
from core.runtime_policy import active_runtime_policy
from support.capacity_calibration_fixture import synthetic_capacity_source_binding


def _capacity_throughput_row(
    *,
    carrier: str,
    measured_scale: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> dict[str, object]:
    row: dict[str, object] = {
        "carrier": carrier,
        "measuredScale": measured_scale,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "throughputUnit": "objects_per_second_per_slot",
        "perSlotThroughputSamples": [0.01] * 10,
        "evidenceRef": "data/local/campaign/resource-soak.json",
        "evidenceDigest": "sha256:" + "2" * 64,
    }
    row["throughputBasisDigest"] = throughput_basis_digest(row)
    return row


def _patch_envelope_deps(monkeypatch) -> None:
    monkeypatch.setattr(
        envelopes,
        "_require_stable_source_inputs",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(envelopes, "_git_branch", lambda _repo: "dev1.0")
    monkeypatch.setattr(
        envelopes,
        "_git_commit",
        lambda _repo: "0123456789abcdef0123456789abcdef01234567",
    )
    frozen_snapshot = SourceDefinitionSnapshot(digest="sha256:" + ("a" * 64))
    for module in (envelopes, request_envelope_build):
        monkeypatch.setattr(
            module,
            "current_source_definition_snapshot",
            lambda repo_root=None: frozen_snapshot,
        )
    monkeypatch.setattr(
        request_envelope_build,
        "entity_catalog_digest",
        lambda _ref: "sha256:" + ("b" * 64),
    )
    monkeypatch.setattr(
        request_envelope_build,
        "bind_capacity_calibration_source",
        lambda **kwargs: synthetic_capacity_source_binding(
            provider_tier=str(kwargs["provider_tier"]),
        ),
    )
    fixture_handoff_document = {
        "vertical": "travel",
        "regionRef": "china",
        "lifecycle": "research",
        "scopeType": "region",
        "scope": "china",
        "primaryTopicRef": None,
        "relatedTopicRefs": [],
        "handoffId": "local-contract",
        "handoffRevision": 1,
        "handoffDigest": "sha256:" + "9" * 64,
        "sourceSelection": {
            carrier: {"mode": "site_primary", "providers": ["wikipedia"]}
            for carrier in ("homepage", "article", "image", "video")
        },
    }
    fixture_handoff_binding = {
        "handoffId": "local-contract",
        "handoffRevision": 1,
        "handoffRef": (
            "data/local/workspace/content-pre-acquisition-handoffs/"
            "local-contract/revision-001.json"
        ),
        "handoffDigest": "sha256:" + "9" * 64,
        "handoffFileDigest": "sha256:" + "8" * 64,
    }
    monkeypatch.setattr(
        request_envelope_build,
        "load_pre_acquisition_handoff",
        lambda _path: dict(fixture_handoff_document),
    )
    monkeypatch.setattr(
        request_envelope_writer,
        "load_pre_acquisition_handoff",
        lambda _path: dict(fixture_handoff_document),
    )
    monkeypatch.setattr(
        request_envelope_build,
        "freeze_carrier_pre_acquisition_inputs",
        lambda *_args, **_kwargs: (
            [],
            dict(fixture_handoff_document),
            dict(fixture_handoff_binding),
        ),
    )
    def bind_pool(_path: Path, **kwargs: object):
        carrier = str(kwargs["carrier"])
        count = int(kwargs["count"])
        binding = {
            "poolId": "pool-local-contract",
            "targetScale": str(kwargs["target_scale"]),
            "workloadMode": (
                "explicit"
                if str(kwargs["target_scale"]) == "WORKLOAD"
                else "milestone_preset"
            ),
            "activeCarriers": list(kwargs.get("active_carriers") or (carrier,)),
            "workloadTargets": dict(kwargs.get("workload_targets") or {carrier: count}),
            "sourceRevision": str(kwargs["source_revision"]),
            "sourceDigest": str(kwargs["source_digest"]),
            "entityCatalogDigest": str(kwargs["entity_catalog_digest"]),
            "planRef": "data/local/workspace/source-pool/plan.json",
            "planDigest": "sha256:" + "4" * 64,
            "planFileSha256": "sha256:" + "5" * 64,
        }
        selection = {
            "carrier": carrier,
            "candidateIds": [f"{carrier}-{index:05d}" for index in range(count)],
            "candidateCount": count,
            "selectionDigest": "sha256:" + "6" * 64,
        }
        return binding, "data/local/workspace/source-pool/evidence", selection

    monkeypatch.setattr(request_envelope_build, "bind_scale_source_pool", bind_pool)
    original_build = request_envelope_build.build_envelope

    def _governed_workload(kwargs: dict[str, object]) -> bool:
        """Mirror the builder's authority split: bounded covers small explicit."""
        if str(kwargs.get("workload_mode") or "explicit") != "explicit":
            return True
        resolved = resolve_campaign_scale(
            scale=kwargs.get("scale"),  # type: ignore[arg-type]
            quota=kwargs.get("quota"),  # type: ignore[arg-type]
        )
        active = tuple(kwargs.get("active_carriers") or (kwargs["carrier"],))
        workloads = kwargs.get("workloads")
        if workloads is None:
            total = resolved.quota * len(active)
        else:
            total = sum(int(value) for value in dict(workloads).values())  # type: ignore[call-overload]
        return total > 10

    def build_with_capacity(**kwargs: object):
        if not kwargs.get("capacity_calibration_receipt") and _governed_workload(
            kwargs
        ):
            kwargs["capacity_calibration_receipt"] = Path(
                "data/local/tests/capacity/local-contract-capacity.json"
            )
        if not kwargs.get("pre_acquisition_handoff"):
            kwargs["pre_acquisition_handoff"] = Path(
                "data/local/workspace/content-pre-acquisition-handoffs/"
                "local-contract/revision-001.json"
            )
        return original_build(**kwargs)

    monkeypatch.setattr(request_envelope_build, "build_envelope", build_with_capacity)
    monkeypatch.setattr(request_envelope_writer, "build_envelope", build_with_capacity)
    monkeypatch.setattr(envelopes, "build_envelope", build_with_capacity)
    original_write = request_envelope_writer.write_scale_envelopes

    def write_with_handoff(*args: object, **kwargs: object):
        if not kwargs.get("pre_acquisition_handoff"):
            kwargs["pre_acquisition_handoff"] = Path(
                "data/local/workspace/content-pre-acquisition-handoffs/"
                "local-contract/revision-001.json"
            )
        return original_write(*args, **kwargs)

    monkeypatch.setattr(
        request_envelope_writer, "write_scale_envelopes", write_with_handoff
    )
    monkeypatch.setattr(envelopes, "write_scale_envelopes", write_with_handoff)
    monkeypatch.setattr(m100_alpha_acceptance, "assert_valid", lambda *_args, **_kwargs: None)


def _pool_kwargs(tmp_path: Path) -> dict[str, Path]:
    return {
        "scale_source_pool": tmp_path / "pool.json",
        "source_pool_evidence_root": tmp_path / "evidence",
    }


def _expected_count(quota: int) -> int:
    return math.ceil(quota * active_runtime_policy().oversample_factor)


def _wave_targets(prefix: str = "wave", count: int = 12) -> tuple[str, ...]:
    return tuple(f"{prefix}-target-{index:03d}" for index in range(count))


def _research_m100_receipt(path: Path, *, source_digest: str | None = None) -> Path:
    output_root = path
    path = (
        research_scale_promotions_root(output_root=output_root)
        / "research-release-1"
        / "research-m100-1"
        / "research-m100.json"
    )
    semantic_jobs = [
        {
            "carrier": carrier,
            "executionId": f"20260805--travel-{carrier}-m100--china--scale-001",
            "semanticJobCount": 10,
            "semanticJobSucceededCount": 10,
            "semanticJobTerminalCount": 10,
            "semanticJobIds": [
                f"{carrier}-job-{index:02d}" for index in range(10)
            ],
            "semanticJobSucceededIds": [
                f"{carrier}-job-{index:02d}" for index in range(10)
            ],
            "semanticJobTerminalIds": [
                f"{carrier}-job-{index:02d}" for index in range(10)
            ],
            "perSlotThroughputSamples": [0.01] * 10,
            "activeDurationSeconds": 3600,
            "activeIntervals": [
                {
                    "startedAt": "2026-08-05T00:00:00Z",
                    "endedAt": "2026-08-05T01:00:00Z",
                    "durationSeconds": 3600,
                }
            ],
        }
        for carrier in ("homepage", "article", "image", "video")
    ]
    semantic_calibration = [
        {
            "carrier": carrier,
            "provider": "codex_sdk",
            "authorModel": "gpt-5.6-terra",
            "authorModelFamily": "gpt",
            "reviewerModel": "gpt-5.6-terra",
            "reviewerModelFamily": "gpt",
            "calibrationProvider": "codex_sdk",
            "calibrationModel": "gpt-5.6-sol",
            "calibrationModelFamily": "gpt",
            "executionManifestRef": f"data/tasks/{carrier}/execution_manifest.json",
            "executionManifestSha256": "sha256:" + "4" * 64,
            "authorRun": {
                "objectRef": f"{carrier}-primary-object",
                "runId": f"{carrier}-terra-author-run",
                "evidenceRef": f"data/tasks/{carrier}/4.draft/agent_result_envelope.json",
                "evidenceSha256": "sha256:" + "5" * 64,
            },
            "reviewerRun": {
                "objectRef": f"{carrier}-primary-object",
                "runId": f"{carrier}-terra-reviewer-run",
                "evidenceRef": f"data/tasks/{carrier}/5.review/reviewer_result.json",
                "evidenceSha256": "sha256:" + "6" * 64,
            },
            "selectionPolicy": {
                "sampleRate": 0.1,
                "minimumSampleCount": 10,
                "smallBatchPolicy": "all",
                "acceptedObjectCount": 10 if carrier == "video" else 100,
                "requiredSampleCount": 10,
                "selectedObjectRefs": [
                    f"{carrier}-calibration-object-{index:02d}"
                    for index in range(10)
                ],
                "selectionDigest": "sha256:" + "7" * 64,
            },
            "calibrationRuns": [
                {
                    "objectRef": f"{carrier}-calibration-object-{index:02d}",
                    "runId": f"{carrier}-sol-calibration-run-{index:02d}",
                    "evidenceRef": (
                        f"data/tasks/{carrier}/evidence/semantic_calibration/"
                        f"{index:02d}.reviewer_result.json"
                    ),
                    "evidenceSha256": "sha256:" + "8" * 64,
                }
                for index in range(10)
            ],
        }
        for carrier in ("homepage", "article", "image", "video")
    ]
    write_json(
        path,
        {
            "schema": "quwoquan_data.research_scale_promotion",
            "promotionId": "research-m100-1",
            "releaseId": "research-release-1",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "manifestDigest": "sha256:" + ("c" * 64),
            "sourceRevision": content_source_revision(
                source_digest=source_digest or ("sha256:" + ("a" * 64)),
                entity_catalog_digest="sha256:" + ("b" * 64),
            ),
            "sourceDigest": source_digest or ("sha256:" + ("a" * 64)),
            "entityCatalogDigest": "sha256:" + ("b" * 64),
            "targetScale": "M100",
            "sourcePoolDigest": "sha256:" + "4" * 64,
            "predecessorSourcePoolDigests": [],
            "scaleStartedAt": "2026-08-05T00:00:00Z",
            "scaleCompletedAt": "2026-08-05T01:01:00Z",
            "wallClockBudgetSeconds": None,
            "wallClockSeconds": 3660,
            "capacityThroughputByCarrier": [
                _capacity_throughput_row(
                    carrier=carrier,
                    measured_scale="M100",
                    source_revision=content_source_revision(
                        source_digest=source_digest or ("sha256:" + ("a" * 64)),
                        entity_catalog_digest="sha256:" + ("b" * 64),
                    ),
                    source_digest=source_digest or ("sha256:" + ("a" * 64)),
                    entity_catalog_digest="sha256:" + ("b" * 64),
                )
                for carrier in ("homepage", "article", "image", "video")
            ],
            "carrierCounts": [
                {
                    "carrier": carrier,
                    "targetCount": 10 if carrier == "video" else 100,
                    "qualifiedCount": 10 if carrier == "video" else 100,
                    "finalizedCount": 10 if carrier == "video" else 100,
                    "predecessorCarriedCount": 0,
                    "newFinalizedCount": 10 if carrier == "video" else 100,
                    "totalUniqueFinalizedCount": 10 if carrier == "video" else 100,
                    "selectedCount": 10 if carrier == "video" else 100,
                    "discardedCount": 0,
                    "shortfallCount": 0,
                    "researchAcceptedCount": 10 if carrier == "video" else 100,
                }
                for carrier in ("homepage", "article", "image", "video")
            ],
            "statistics": {
                "objectPassRate": {
                    "numerator": 310,
                    "denominator": 310,
                    "rate": 1.0,
                },
                "illustratedRate": {
                    "statistical": True,
                    "nonBlocking": True,
                    "numerator": 90,
                    "denominator": 100,
                    "rate": 0.9,
                },
                "textOnlyRate": {
                    "statistical": True,
                    "nonBlocking": True,
                    "numerator": 10,
                    "denominator": 100,
                    "rate": 0.1,
                },
                "videoPopularity": {
                    "statistical": True,
                    "nonBlocking": True,
                    "signalAvailability": [
                        {
                            "signal": signal,
                            "numerator": 10,
                            "denominator": 10,
                            "rate": 1.0,
                        }
                        for signal in ("play", "like", "comment", "share", "favorite")
                    ],
                    "rankingCoverage": {
                        "numerator": 10,
                        "denominator": 10,
                        "rate": 1.0,
                    },
                    "observations": [
                        {
                            "objectRef": "posts/video/example",
                            "assetId": "video-asset-1",
                            "playCount": 100,
                            "likeCount": 10,
                            "commentCount": 2,
                            "shareCount": 1,
                            "favoriteCount": 3,
                            "observedAt": "2026-08-05T00:00:00Z",
                            "comparisonBucket": {
                                "provider": "fixture",
                                "topic": "travel",
                                "timeBucket": "2026-W32",
                                "candidateCount": 10,
                            },
                            "popularityScore": 451,
                            "popularityPercentile": 1.0,
                            "rankingEligible": True,
                            "ineligibleReason": "",
                        }
                    ],
                    "observationIssues": [],
                },
                "automaticRecoveryRate": {
                    "statistical": True,
                    "nonBlocking": True,
                    "status": "MEASURED",
                    "eligibleCount": 20,
                    "automaticCount": 19,
                    "targetRate": 0.95,
                    "rate": 0.95,
                },
                "firstPassRate": {
                    "numerator": 4,
                    "denominator": 4,
                    "rate": 1.0,
                },
                "discardRate": {
                    "numerator": 0,
                    "denominator": 310,
                    "rate": 0.0,
                },
                "quotaAttainmentByCarrier": [
                    {
                        "carrier": carrier,
                        "numerator": 10 if carrier == "video" else 100,
                        "denominator": 10 if carrier == "video" else 100,
                        "rate": 1.0,
                    }
                    for carrier in ("homepage", "article", "image", "video")
                ],
            },
            "professionalImageSourceMix": {
                "statistical": True,
                "nonBlocking": True,
                "acceptedImageAssetCount": 100,
                "originalAssetClosureCount": 100,
                "pinterestAcceptedAssetCount": 60,
                "tuchongAcceptedAssetCount": 20,
                "pinterestTuchongAcceptedAssetCount": 80,
                "pinterestTuchongAcceptedAssetRatio": 0.8,
                "largestProvider": "pinterest",
                "maxProviderAcceptedAssetRatio": 0.6,
                "providerAssetCounts": [
                    {"provider": "pinterest", "acceptedAssetCount": 60, "acceptedAssetRatio": 0.6},
                    {"provider": "tuchong", "acceptedAssetCount": 20, "acceptedAssetRatio": 0.2},
                    {"provider": "wikimedia commons", "acceptedAssetCount": 20, "acceptedAssetRatio": 0.2},
                ],
                "policyObservations": {
                    "pinterestUniqueLargest": True,
                    "tuchongPresent": True,
                    "pinterestTuchongAtLeastHalf": True,
                    "providerAboveSeventyPercent": [],
                },
                "observationIssues": [],
            },
            "duplicateAssetCount": 0,
            "crossLaneWriteCount": 0,
            "resourceIsolationPassed": True,
            "soakDurationSeconds": 3600,
            "semanticJobsByLane": semantic_jobs,
            "semanticCalibrationByLane": semantic_calibration,
            "fourLaneOverlapSampleCount": 1,
            "fourLaneOverlapDurationSeconds": 3600,
            "fourLaneLongestContinuousOverlapSeconds": 3600,
            "allSemanticJobsTerminalAt": "2026-08-05T01:00:00Z",
            "terminalResidualSampleAt": "2026-08-05T01:01:00Z",
            "campaignEvidenceRef": "data/local/campaign/evidence.json",
            "campaignEvidenceDigest": "sha256:" + "1" * 64,
            "resourceSoakEvidenceRef": "data/local/campaign/resource-soak.json",
            "resourceSoakEvidenceDigest": "sha256:" + "2" * 64,
            "faultInjectionEvidenceRef": "data/local/campaign/fault-injection.json",
            "faultInjectionEvidenceDigest": "sha256:" + "3" * 64,
            "nextScaleEligible": "M1000",
            "recordedAt": "2026-08-05T00:00:00Z",
        },
    )
    return path


def _promotion_output_root(path: Path) -> Path:
    suffix = Path("data/local/workspace/research-scale/promotions")
    parts = path.resolve().parts
    marker = suffix.parts
    for index in range(len(parts) - len(marker) + 1):
        if parts[index : index + len(marker)] == marker:
            return Path(*parts[:index])
    raise AssertionError(f"promotion fixture is not canonical: {path}")
