"""Aggregate release evidence uses one frozen, closed-vocabulary receipt."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.control_types import RolloutMilestone  # noqa: E402
from core.source_digest import current_source_digest  # noqa: E402
from content.release.canonical.release_attestation import (  # noqa: E402
    ReleaseAttestation,
    ReleaseAttestationError,
)
from content.release.model import ReleaseKind  # noqa: E402


def _receipt() -> ReleaseAttestation:
    return ReleaseAttestation(
        release_id="20260718--travel-homepage-coverage--cn-zhejiang-sichuan--canary-001",
        release_kind=ReleaseKind.CONTENT,
        execution_ids=(
            "20260718--travel-homepage-coverage--cn-zhejiang--canary-001",
            "20260718--travel-homepage-coverage--cn-sichuan--canary-001",
        ),
        rollout_milestone=RolloutMilestone.CANARY,
        entity_count=3,
        post_count=9,
        creator_count=3,
        tag_count=0,
        canonical_merkle="sha256:" + "a" * 64,
        source_digest=current_source_digest(),
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
            "releaseId": "20260718--travel-article-cold-start--cn-zhejiang--m1-001",
            "executionIds": [
                "20260718--travel-article-cold-start--cn-zhejiang--m1-001"
            ],
            "rolloutMilestone": RolloutMilestone.M1.value,
            "entityCount": 0,
            "postCount": 100,
        }
    )

    receipt = ReleaseAttestation.from_document(document)

    assert receipt.entity_count == 0
    assert receipt.post_count == 100


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
    document["rolloutMilestone"] = RolloutMilestone.BASELINE.value

    try:
        ReleaseAttestation.from_document(document)
    except ReleaseAttestationError as exc:
        assert "empty baseline" in str(exc)
    else:
        raise AssertionError("empty baseline cannot carry content receipt fields")
