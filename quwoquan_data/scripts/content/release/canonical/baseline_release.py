"""Immutable empty baseline release for data-owned environment rollback."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from core.release_layout import attestation_root, payload_digest, payload_file, payload_root
from core.schema import assert_valid
from core.tree_integrity import tree_integrity_stats
from content.release.canonical.object_transaction_contract import (
    RELEASE_SCHEMA,
    ObjectTransactionError,
    _now,
    _read_json,
    _safe_id,
    _write_json,
    assert_environment_neutral,
)


EMPTY_BASELINE_RELEASE_KIND = "empty_baseline"
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
    release_id = _safe_id(release_id, label="releaseId")
    final_root = release_root / release_id
    canonical = tree_integrity_stats(publish_root)
    if final_root.exists():
        header = _read_json(payload_file(final_root, "release.json"))
        desired = _read_json(payload_file(final_root, "desired_state.json"))
        if (
            header.get("releaseId") == release_id
            and header.get("releaseKind") == EMPTY_BASELINE_RELEASE_KIND
            and header.get("canonicalMerkle") == canonical["merkleRoot"]
            and header.get("executionIds") == []
            and header.get("rolloutMilestone") == "baseline"
            and desired.get("desiredRefs") == _EMPTY_DESIRED_REFS
        ):
            return {
                "schemaVersion": "quwoquan_data.empty_baseline_release_result/1",
                "releaseId": release_id,
                "releaseRoot": str(final_root),
                "releaseKind": EMPTY_BASELINE_RELEASE_KIND,
                "idempotent": True,
            }
        raise ObjectTransactionError(f"empty baseline release create-once conflict: {final_root}")

    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=final_root.parent))
    try:
        payload = payload_root(staging)
        _write_json(
            payload / "release.json",
            {
                "schemaVersion": RELEASE_SCHEMA,
                "releaseId": release_id,
                "releaseKind": EMPTY_BASELINE_RELEASE_KIND,
                "canonicalMerkle": canonical["merkleRoot"],
                "executionIds": [],
                "rolloutMilestone": "baseline",
            },
        )
        _write_json(
            payload / "desired_state.json",
            {
                "schemaVersion": "quwoquan_data.release_desired_state/1",
                "releaseId": release_id,
                "desiredRefs": _EMPTY_DESIRED_REFS,
            },
        )
        _write_json(
            payload / "index/objects.json",
            {"schemaVersion": "quwoquan_data.release_object_index/1", **_EMPTY_DESIRED_REFS},
        )
        _write_json(
            payload / "sample_bundle.json",
            {
                "schemaVersion": "quwoquan_data.release_sample_bundle/1",
                "entities": [],
                "posts": [],
                "tags": [],
            },
        )
        _write_json(
            payload / "media_manifest.json",
            {
                "schemaVersion": "quwoquan_data.release_media_manifest/1",
                "releaseId": release_id,
                "assets": [],
                "issues": [],
            },
        )
        aggregate_attestation = {
            "schemaVersion": "quwoquan_data.aggregate_release_attestation/2",
            "releaseId": release_id,
            "releaseKind": EMPTY_BASELINE_RELEASE_KIND,
            "executionIds": [],
            "rolloutMilestone": "baseline",
            "entityCount": 0,
            "tagCount": 0,
            "canonicalMerkle": canonical["merkleRoot"],
            "payloadSha256": payload_digest(staging),
            "recordedAt": _now(),
        }
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
            "schemaVersion": "quwoquan_data.empty_baseline_release_result/1",
            "releaseId": release_id,
            "releaseRoot": str(final_root),
            "releaseKind": EMPTY_BASELINE_RELEASE_KIND,
            "idempotent": False,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
