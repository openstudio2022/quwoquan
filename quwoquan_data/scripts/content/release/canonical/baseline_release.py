"""Immutable empty baseline release for data-owned environment rollback."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    RELEASE_SCHEMA,
    ObjectTransactionError,
    _now,
    _read_json,
    _safe_id,
    _write_json,
    assert_environment_neutral,
)
from content.release.canonical.release_admission import (
    build_release_asset_admission,
)
from content.release.canonical.release_attestation import ReleaseAttestation
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.release_identity_incident import (
    canonical_release_identity_guard,
    release_output_root,
)
from content.release.model import DataSourceOwner, ReleaseKind
from core.release_layout import (
    attestation_root,
    objects_merkle,
    payload_digest,
    payload_file,
    payload_root,
)
from core.schema import assert_valid
from core.source_digest import current_source_definition_snapshot
from governance.coverage.distribution import ProductLifecycleState, ReleaseClass

_EMPTY_DESIRED_REFS = {"creators": [], "entities": [], "posts": [], "tags": []}


def _build_empty_baseline_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    release_class: str,
) -> dict[str, Any]:
    """Create one immutable empty desired state for data-owned rollback.

    The payload is a real release rather than an ad-hoc empty directory. Syncing
    it clears only the importer-owned data projection and leaves unrelated
    service records untouched.
    """
    del publish_root
    release_id = _safe_id(release_id, label="releaseId")
    release_mode = str(release_class or "").strip()
    if release_mode not in {"research", "commercial"}:
        raise ObjectTransactionError(
            f"DATA.RELEASE.CLASS_INVALID: {release_mode!r}"
        )
    source_digest = current_source_definition_snapshot()
    final_root = release_root / release_id
    if final_root.exists():
        header = _read_json(payload_file(final_root, "release.json"))
        desired = _read_json(payload_file(final_root, "desired_state.json"))
        aggregate = _read_json(attestation_root(final_root) / "release.json")
        if (
            header.get("releaseId") == release_id
            and header.get("releaseKind") == ReleaseKind.EMPTY_BASELINE
            and header.get("releaseClass") == release_mode
            and header.get("productLifecycleState") == release_mode
            and header.get("sourceOwner") == DataSourceOwner.QWQ_DATA
            and header.get("canonicalMerkle") == objects_merkle(final_root)
            and header.get("executionIds") == []
            and header.get("sourceDigests") == [source_digest.to_document()]
            and aggregate.get("sourceDigests") == [source_digest.to_document()]
            and aggregate.get("sourceOwner") == DataSourceOwner.QWQ_DATA
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
        asset_admission = build_release_asset_admission(
            release_id=release_id,
            objects_root=payload / "objects",
            desired=_EMPTY_DESIRED_REFS,
            release_class=release_mode,
        )
        assert_valid(
            asset_admission,
            "release",
            "release_asset_admission",
            label=f"release_asset_admission:{release_id}",
        )
        _write_json(payload / "asset_admission.json", asset_admission)
        canonical_merkle = objects_merkle(staging, create=True)
        release_header = {
            "schema": RELEASE_SCHEMA,
            "releaseId": release_id,
            "sourceOwner": DataSourceOwner.QWQ_DATA,
            "releaseKind": ReleaseKind.EMPTY_BASELINE,
            "releaseClass": release_mode,
            "productLifecycleState": release_mode,
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": asset_admission["rightsStatusCounts"],
            "authorizationRequiredAssetIds": [],
            "researchAcceptedCount": 0,
            "commercialAcceptedCount": 0,
            "canonicalMerkle": canonical_merkle,
            "executionIds": [],
            "sourceDigests": [source_digest.to_document()],
        }
        desired_state = {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": _EMPTY_DESIRED_REFS,
        }
        validate_release_header(
            release_header,
            label=f"release_header:{release_id}",
        )
        assert_valid(
            desired_state,
            "release",
            "release_desired_state",
            label=f"release_desired_state:{release_id}",
        )
        _write_json(payload / "release.json", release_header)
        _write_json(payload / "desired_state.json", desired_state)
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
                "sourceOwner": "qwq_data",
                "assets": [],
                "issues": [],
                "counts": {"assets": 0, "issues": 0},
            },
        )
        release_attestation = ReleaseAttestation(
            release_id=release_id,
            source_owner=DataSourceOwner.QWQ_DATA,
            release_kind=ReleaseKind.EMPTY_BASELINE,
            release_class=ReleaseClass(release_mode),
            product_lifecycle_state=ProductLifecycleState(release_mode),
            contains_unverified_assets=False,
            rights_status_counts=dict(asset_admission["rightsStatusCounts"]),
            authorization_required_asset_ids=(),
            research_accepted_count=0,
            commercial_accepted_count=0,
            execution_ids=(),
            entity_count=0,
            post_count=0,
            creator_count=0,
            tag_count=0,
            canonical_merkle=canonical_merkle,
            source_revision=None,
            source_digest=None,
            entity_catalog_digest=None,
            source_digests=(source_digest,),
            payload_sha256=payload_digest(staging),
            recorded_at=_now(),
        ).to_document()
        assert_valid(
            release_attestation,
            "release",
            "release_attestation",
            label=f"release_attestation:{release_id}",
        )
        _write_json(attestation_root(staging) / "release.json", release_attestation)
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


def build_empty_baseline_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    release_class: str,
) -> dict[str, Any]:
    """Guard empty-baseline creation against a collided content identity."""

    with canonical_release_identity_guard(
        output_root=release_output_root(release_root),
        release_id=release_id,
    ):
        return _build_empty_baseline_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id=release_id,
            release_class=release_class,
        )
