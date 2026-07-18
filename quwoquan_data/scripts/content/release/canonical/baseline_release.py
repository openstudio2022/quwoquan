"""Immutable empty baseline release for data-owned environment rollback."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from core.release_layout import (
    attestation_root,
    object_closure_digest,
    payload_digest,
    payload_file,
    payload_root,
)
from core.control_types import RolloutMilestone
from core.schema import assert_valid
from core.source_digest import current_source_digest
from content.release.canonical.object_transaction_contract import (
    RELEASE_SCHEMA,
    ObjectTransactionError,
    _now,
    _read_json,
    _safe_id,
    _write_json,
    assert_environment_neutral,
)
from content.release.canonical.release_attestation import ReleaseAttestation
from content.release.model import ReleaseKind


_EMPTY_DESIRED_REFS = {"creators": [], "entities": [], "posts": [], "tags": []}


def build_empty_baseline_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
) -> dict[str, Any]:
    """Create one immutable empty desired state for data-owned rollback.

    The payload is a real release rather than an ad-hoc empty directory. Syncing
    it clears only the importer-owned data projection and leaves unrelated
    service records untouched.
    """
    del publish_root
    release_id = _safe_id(release_id, label="releaseId")
    source_digest = current_source_digest()
    final_root = release_root / release_id
    if final_root.exists():
        header = _read_json(payload_file(final_root, "release.json"))
        desired = _read_json(payload_file(final_root, "desired_state.json"))
        aggregate = _read_json(attestation_root(final_root) / "aggregate.json")
        if (
            header.get("releaseId") == release_id
            and header.get("releaseKind") == ReleaseKind.EMPTY_BASELINE
            and header.get("canonicalMerkle") == object_closure_digest(final_root)
            and header.get("executionIds") == []
            and header.get("rolloutMilestone") == "baseline"
            and header.get("sourceDigest") == source_digest.to_document()
            and aggregate.get("sourceDigest") == source_digest.to_document()
            and desired.get("desiredRefs") == _EMPTY_DESIRED_REFS
            and aggregate.get("payloadSha256") == payload_digest(final_root)
        ):
            return {
                "schema": "quwoquan_data.empty_baseline_release_result",
                "releaseId": release_id,
                "releaseRoot": str(final_root),
                "releaseKind": ReleaseKind.EMPTY_BASELINE,
                "idempotent": True,
            }
        raise ObjectTransactionError(f"empty baseline release create-once conflict: {final_root}")

    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=final_root.parent))
    try:
        payload = payload_root(staging)
        canonical_merkle = object_closure_digest(staging, create=True)
        _write_json(
            payload / "release.json",
            {
                "schema": RELEASE_SCHEMA,
                "releaseId": release_id,
                "releaseKind": ReleaseKind.EMPTY_BASELINE,
                "canonicalMerkle": canonical_merkle,
                "executionIds": [],
                "rolloutMilestone": "baseline",
                "sourceDigest": source_digest.to_document(),
            },
        )
        _write_json(
            payload / "desired_state.json",
            {
                "schema": "quwoquan_data.release_desired_state",
                "releaseId": release_id,
                "desiredRefs": _EMPTY_DESIRED_REFS,
            },
        )
        _write_json(
            payload / "index/objects.json",
            {"schema": "quwoquan_data.release_object_index", **_EMPTY_DESIRED_REFS},
        )
        _write_json(
            payload / "sample_bundle.json",
            {
                "schema": "quwoquan_data.release_sample_bundle",
                "entities": [],
                "posts": [],
                "tags": [],
            },
        )
        _write_json(
            payload / "media_manifest.json",
            {
                "schema": "quwoquan_data.release_media_manifest",
                "releaseId": release_id,
                "assets": [],
                "issues": [],
            },
        )
        aggregate_attestation = ReleaseAttestation(
            release_id=release_id,
            release_kind=ReleaseKind.EMPTY_BASELINE,
            execution_ids=(),
            rollout_milestone=RolloutMilestone.BASELINE,
            entity_count=0,
            post_count=0,
            creator_count=0,
            tag_count=0,
            canonical_merkle=canonical_merkle,
            source_digest=source_digest,
            payload_sha256=payload_digest(staging),
            recorded_at=_now(),
        ).to_document()
        assert_valid(
            aggregate_attestation,
            "release",
            "aggregate_release_attestation",
            label=f"aggregate_release_attestation:{release_id}",
        )
        _write_json(attestation_root(staging) / "aggregate.json", aggregate_attestation)
        assert_environment_neutral(staging)
        staging.replace(final_root)
        return {
            "schema": "quwoquan_data.empty_baseline_release_result",
            "releaseId": release_id,
            "releaseRoot": str(final_root),
            "releaseKind": ReleaseKind.EMPTY_BASELINE,
            "idempotent": False,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
