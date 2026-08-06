"""Aggregate release evidence uses one frozen, closed-vocabulary receipt."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.release_attestation import (
    ReleaseAttestation,
    ReleaseAttestationError,
)
from core.source_digest import (
    content_source_revision,
    current_source_digest,
)

ENTITY_CATALOG_DIGEST = "sha256:" + "e" * 64
from content.release.model import DataSourceOwner, ReleaseKind
from governance.coverage.distribution import (
    ProductLifecycleState,
    ReleaseClass,
)


def _receipt() -> ReleaseAttestation:
    source_digest = current_source_digest()
    return ReleaseAttestation(
        release_id="20260718--travel-homepage-coverage--test-release-a--001",
        source_owner=DataSourceOwner.QWQ_DATA,
        release_kind=ReleaseKind.CONTENT,
        release_class=ReleaseClass.RESEARCH,
        product_lifecycle_state=ProductLifecycleState.RESEARCH,
        contains_unverified_assets=True,
        rights_status_counts={
            "verified": 0,
            "unverified": 12,
            "restricted": 0,
            "unknown": 0,
        },
        authorization_required_asset_ids=("asset-unverified",),
        research_accepted_count=12,
        commercial_accepted_count=0,
        execution_ids=(
            "20260718--travel-homepage-coverage--test-region-a--pilot-001",
            "20260718--travel-homepage-coverage--test-region-b--pilot-001",
        ),
        entity_count=3,
        post_count=9,
        creator_count=3,
        tag_count=0,
        canonical_merkle="sha256:" + "a" * 64,
        source_revision=content_source_revision(
            source_digest=source_digest.digest,
            entity_catalog_digest=ENTITY_CATALOG_DIGEST,
        ),
        source_digest=source_digest.digest,
        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
        source_digests=(source_digest,),
        payload_sha256="sha256:" + "b" * 64,
        recorded_at="2026-07-18T00:00:00Z",
    )


def test_release_attestation__typed_receipt__contract__local_contract() -> None:
    document = _receipt().to_document()

    assert ReleaseAttestation.from_document(document) == _receipt()


def test_release_attestation__allows_post_only_lane_release__contract__local_contract() -> None:
    document = _receipt().to_document()
    document.update(
        {
            "releaseId": "20260718--travel-article-supply--test-release-b--001",
            "executionIds": [
                "20260718--travel-article-supply--test-region-a--scale-001"
            ],
            "entityCount": 0,
            "postCount": 100,
        }
    )

    receipt = ReleaseAttestation.from_document(document)

    assert receipt.entity_count == 0
    assert receipt.post_count == 100


def test_release_attestation__rejects_mixed_execution_source_digests__contract() -> None:
    document = _receipt().to_document()
    second_digest = dict(document["sourceDigests"][0])
    second_digest["digest"] = "sha256:" + "c" * 64
    document["sourceDigests"] = sorted(
        [document["sourceDigests"][0], second_digest],
        key=lambda item: item["digest"],
    )

    try:
        ReleaseAttestation.from_document(document)
    except ReleaseAttestationError as exc:
        assert "exactly one sourceDigest" in str(exc)
    else:
        raise AssertionError("mixed sourceDigest content release must block")


def test_release_attestation__rejects_content_without_objects__contract__local_contract() -> None:
    document = _receipt().to_document()
    document["entityCount"] = 0
    document["postCount"] = 0

    try:
        ReleaseAttestation.from_document(document)
    except ReleaseAttestationError as exc:
        assert "canonical entities or posts" in str(exc)
    else:
        raise AssertionError("content release without canonical objects must block")


def test_release_attestation__rejects_baseline_with_objects__contract__local_contract() -> None:
    document = _receipt().to_document()
    document["releaseKind"] = ReleaseKind.EMPTY_BASELINE.value

    try:
        ReleaseAttestation.from_document(document)
    except ReleaseAttestationError as exc:
        assert "empty baseline" in str(exc)
    else:
        raise AssertionError("empty baseline cannot carry content receipt fields")
