from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.canonical.commercial_transition import (
    CommercialTransitionError,
    write_commercial_transition,
)
from content.release.canonical.research_scale_promotion import (
    ResearchScalePromotionError,
    write_research_scale_promotion,
)
from core.release_layout import payload_digest


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _research_release(output_root: Path, *, article_count: int = 100) -> Path:
    release = output_root / "data/releases/research-release"
    carrier_counts = [
        {
            "carrier": carrier,
            "researchAcceptedCount": article_count if carrier == "article" else 100,
        }
        for carrier in ("homepage", "article", "image", "video")
    ]
    _write(
        release / "payload/release.json",
        {
            "releaseId": "research-release",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "sourceDigests": [
                {"algorithm": "sha256", "digest": "sha256:" + "a" * 64}
            ],
        },
    )
    _write(
        release / "payload/asset_admission.json",
        {
            "releaseClass": "research",
            "productLifecycleState": "research",
            "authorizationRequiredAssetIds": ["old-unverified"],
            "carrierCounts": carrier_counts,
            "articleMediaCoverage": {"illustratedRate": 0.9},
            "assets": [
                {
                    "assetId": "old-unverified",
                    "objectRef": "posts/image/example",
                    "distributionDecision": "research_allowed",
                }
            ],
        },
    )
    return release


def _commercial_release(output_root: Path) -> Path:
    release = output_root / "data/releases/commercial-release"
    _write(
        release / "payload/release.json",
        {
            "releaseId": "commercial-release",
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "sourceDigests": [
                {"algorithm": "sha256", "digest": "sha256:" + "c" * 64}
            ],
        },
    )
    _write(
        release / "payload/asset_admission.json",
        {
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "containsUnverifiedAssets": False,
            "authorizationRequiredAssetIds": [],
            "assets": [
                {
                    "assetId": "new-verified",
                    "objectRef": "posts/image/example",
                    "distributionDecision": "commercial_allowed",
                }
            ],
        },
    )
    return release


def test_research_m100_promotion_requires_four_carriers_and_recovery_evidence(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    release = _research_release(output_root)
    evidence = output_root / "data/campaigns/campaign-1/m100.json"
    _write(
        evidence,
        {
            "releaseId": "research-release",
            "manifestDigest": payload_digest(release),
            "sourceRevision": "sha256:" + "b" * 64,
            "sourceDigest": "sha256:" + "a" * 64,
            "entityCatalogDigest": "sha256:" + "d" * 64,
            "duplicateAssetCount": 0,
            "crossLaneWriteCount": 0,
            "resourceIsolationPassed": True,
            "automaticRecoveryRate": 0.97,
        },
    )

    document, path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-1",
        campaign_evidence_path=evidence,
        release_root=output_root / "data/releases",
        output_root=output_root,
    )

    assert document["m1000Eligible"] is True
    assert document["carrierCounts"] == [
        {"carrier": carrier, "researchAcceptedCount": 100}
        for carrier in ("homepage", "article", "image", "video")
    ]
    assert path.is_file()


def test_research_m100_promotion_blocks_any_carrier_shortfall(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    release = _research_release(output_root, article_count=99)
    evidence = output_root / "data/campaigns/campaign-1/m100.json"
    _write(
        evidence,
        {
            "releaseId": "research-release",
            "manifestDigest": payload_digest(release),
            "sourceRevision": "sha256:" + "b" * 64,
            "sourceDigest": "sha256:" + "a" * 64,
            "entityCatalogDigest": "sha256:" + "d" * 64,
            "duplicateAssetCount": 0,
            "crossLaneWriteCount": 0,
            "resourceIsolationPassed": True,
            "automaticRecoveryRate": 0.97,
        },
    )

    with pytest.raises(ResearchScalePromotionError, match="all four carriers"):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-1",
            campaign_evidence_path=evidence,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def _cleanup_evidence(
    output_root: Path,
    *,
    research_release: Path,
    commercial_release: Path,
    beta_unauthorized_count: int = 0,
) -> Path:
    path = output_root / "env/commercial-transition/cleanup.json"
    research_digest = payload_digest(research_release)
    commercial_digest = payload_digest(commercial_release)
    environment_rows: list[dict[str, object]] = []
    for environment in ("alpha", "beta", "gamma", "prod"):
        cleanup_ref = f"env/{environment}/runs/commercial-transition/cleanup.json"
        readback_ref = f"env/{environment}/runs/commercial-transition/readback.json"
        _write(
            output_root / cleanup_ref,
            {
                "environment": environment,
                "commercialReleaseId": "commercial-release",
                "commercialManifestDigest": commercial_digest,
                "cachePurged": True,
                "mediaCopiesPurged": True,
                "signedUrlsRevoked": True,
            },
        )
        _write(
            output_root / readback_ref,
            {
                "environment": environment,
                "commercialReleaseId": "commercial-release",
                "commercialManifestDigest": commercial_digest,
                "unauthorizedReadbackCount": 0,
                "unauthorizedAssetIds": [],
            },
        )
        environment_rows.append(
            {
                "environment": environment,
                "cachePurged": True,
                "mediaCopiesPurged": True,
                "signedUrlsRevoked": True,
                "unauthorizedReadbackCount": (
                    beta_unauthorized_count if environment == "beta" else 0
                ),
                "cleanupReceiptRef": cleanup_ref,
                "readbackReceiptRef": readback_ref,
            }
        )
    _write(
        path,
        {
            "researchReleaseId": "research-release",
            "researchManifestDigest": research_digest,
            "commercialReleaseId": "commercial-release",
            "commercialManifestDigest": commercial_digest,
            "environments": environment_rows,
        },
    )
    return path


def test_commercial_transition_records_replacement_and_four_environment_cleanup(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _research_release(output_root)
    commercial_release = _commercial_release(output_root)
    cleanup = _cleanup_evidence(
        output_root,
        research_release=research_release,
        commercial_release=commercial_release,
    )

    document, path = write_commercial_transition(
        research_release_id="research-release",
        commercial_release_id="commercial-release",
        transition_run_id="transition-1",
        cleanup_evidence_path=cleanup,
        release_root=output_root / "data/releases",
        output_root=output_root,
    )

    assert document["objectMigrations"] == [
        {
            "researchAssetId": "old-unverified",
            "objectRef": "posts/image/example",
            "action": "replaced",
            "commercialAssetIds": ["new-verified"],
        }
    ]
    assert document["unauthorizedReadbackCount"] == 0
    assert path.is_file()


def test_commercial_transition_blocks_nonzero_unauthorized_readback(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _research_release(output_root)
    commercial_release = _commercial_release(output_root)
    cleanup = _cleanup_evidence(
        output_root,
        research_release=research_release,
        commercial_release=commercial_release,
        beta_unauthorized_count=1,
    )

    with pytest.raises(CommercialTransitionError, match="cleanup is incomplete"):
        write_commercial_transition(
            research_release_id="research-release",
            commercial_release_id="commercial-release",
            transition_run_id="transition-1",
            cleanup_evidence_path=cleanup,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )
