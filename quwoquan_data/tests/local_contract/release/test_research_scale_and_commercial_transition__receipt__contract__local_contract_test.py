from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.release.canonical.commercial_transition import (
    CommercialTransitionError,
    write_commercial_transition,
)
from content.release.canonical.commercial_transition_evidence import (
    CommercialTransitionEvidenceError,
    write_commercial_transition_cleanup_receipt,
    write_commercial_transition_evidence,
    write_commercial_transition_readback_receipt,
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
            "researchAcceptedCount": (
                article_count if carrier == "article" else (50 if carrier == "video" else 100)
            ),
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


def test_research_m100_promotion_rejects_handwritten_boolean_evidence(
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

    with pytest.raises(ResearchScalePromotionError, match="schema violation"):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-1",
            campaign_evidence_path=evidence,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def test_research_m100_promotion_does_not_trust_booleans_despite_release_shortfall(
    tmp_path: Path,
) -> None:
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

    with pytest.raises(ResearchScalePromotionError, match="schema violation"):
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
) -> Path:
    research_digest = payload_digest(research_release)
    commercial_digest = payload_digest(commercial_release)
    environment_receipts: list[tuple[Path, Path]] = []
    for environment in ("alpha", "beta", "gamma", "prod"):
        _cleanup_document, cleanup_path = (
            write_commercial_transition_cleanup_receipt(
                environment=environment,
                run_id="cleanup-1",
                research_release_id="research-release",
                research_manifest_digest=research_digest,
                commercial_release_id="commercial-release",
                commercial_manifest_digest=commercial_digest,
                cache_purged=True,
                media_copies_purged=True,
                signed_urls_revoked=True,
                output_root=output_root,
            )
        )
        _readback_document, readback_path = (
            write_commercial_transition_readback_receipt(
                environment=environment,
                run_id="readback-1",
                research_release_id="research-release",
                research_manifest_digest=research_digest,
                commercial_release_id="commercial-release",
                commercial_manifest_digest=commercial_digest,
                unauthorized_readback_count=0,
                unauthorized_asset_ids=[],
                output_root=output_root,
            )
        )
        environment_receipts.append((cleanup_path, readback_path))
    _document, path = write_commercial_transition_evidence(
        evidence_id="evidence-1",
        research_release_id="research-release",
        research_manifest_digest=research_digest,
        commercial_release_id="commercial-release",
        commercial_manifest_digest=commercial_digest,
        environment_receipts=environment_receipts,
        output_root=output_root,
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
    assert document["cleanupEvidenceDigest"].startswith("sha256:")
    assert document["receiptDigest"].startswith("sha256:")
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
    )
    evidence = json.loads(cleanup.read_text(encoding="utf-8"))
    beta = next(
        row for row in evidence["environments"] if row["environment"] == "beta"
    )
    readback = output_root / beta["readbackReceiptRef"]
    tampered = json.loads(readback.read_text(encoding="utf-8"))
    tampered["unauthorizedReadbackCount"] = 1
    tampered["unauthorizedAssetIds"] = ["old-unverified"]
    _write(readback, tampered)

    with pytest.raises(CommercialTransitionError, match="schema violation"):
        write_commercial_transition(
            research_release_id="research-release",
            commercial_release_id="commercial-release",
            transition_run_id="transition-1",
            cleanup_evidence_path=cleanup,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def test_commercial_transition_rejects_handwritten_boolean_evidence(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _research_release(output_root)
    commercial_release = _commercial_release(output_root)
    path = (
        output_root
        / "data/commercial-transition-evidence/commercial-release/handwritten/evidence.json"
    )
    _write(
        path,
        {
            "researchReleaseId": "research-release",
            "researchManifestDigest": payload_digest(research_release),
            "commercialReleaseId": "commercial-release",
            "commercialManifestDigest": payload_digest(commercial_release),
            "environments": [
                {"environment": environment, "cachePurged": True}
                for environment in ("alpha", "beta", "gamma", "prod")
            ],
        },
    )

    with pytest.raises(CommercialTransitionError, match="schema violation"):
        write_commercial_transition(
            research_release_id="research-release",
            commercial_release_id="commercial-release",
            transition_run_id="transition-1",
            cleanup_evidence_path=path,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def test_commercial_transition_cleanup_receipt_is_create_once(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    common = {
        "environment": "alpha",
        "run_id": "cleanup-1",
        "research_release_id": "research-release",
        "research_manifest_digest": "sha256:" + "a" * 64,
        "commercial_release_id": "commercial-release",
        "commercial_manifest_digest": "sha256:" + "c" * 64,
        "cache_purged": True,
        "media_copies_purged": True,
        "signed_urls_revoked": True,
        "output_root": output_root,
    }
    first, _path = write_commercial_transition_cleanup_receipt(**common)
    second, _path = write_commercial_transition_cleanup_receipt(**common)
    assert second == first

    with pytest.raises(
        CommercialTransitionEvidenceError,
        match="create-once.*identity conflict",
    ):
        write_commercial_transition_cleanup_receipt(
            **{**common, "research_manifest_digest": "sha256:" + "b" * 64}
        )
