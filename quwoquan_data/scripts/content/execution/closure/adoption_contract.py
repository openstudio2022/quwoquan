"""Pure contracts for adopting an immutable, already-reviewed release closure.

This module validates evidence only.  It does not copy canonical objects, write
campaign state, generate content, or mutate a source release.  The later CLI
writer must consume these validators rather than reimplementing their rules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.release_layout import object_closure_digest, payload_digest
from core.schema import assert_valid
from core.source_digest import SourceDigest, SourceDigestError, content_source_revision

from content.execution.closure.adoption_identity import (
    ReleaseIdentityIncident,
    ReleaseIdentityTuple,
    ReviewedClosureAdoptionError,
    ReviewedClosureAdoptionReceipt,
    ReviewedClosureAdoptionRef,
    _is_sha256,
    _read_object,
    _resolve_path,
    _safe_ref,
    _sorted_unique_strings,
    _source_digests,
    _timestamp,
    _typed,
    _validate_digest_field,
    _validate_file_evidence,
    canonical_digest,
    file_digest,
    validate_release_identity_incident,
)

_CARRIERS = ("homepage", "article", "image", "video")
_OBJECT_KINDS = ("creators", "entities", "posts", "tags")
_SOURCE_EVIDENCE_PATHS = {
    "releaseAttestation": "attestations/release.json",
    "releaseHeader": "payload/release.json",
    "desiredState": "payload/desired_state.json",
    "objectIndex": "payload/index/objects.json",
    "mediaManifest": "payload/media_manifest.json",
}


def _desired_refs(value: object, *, label: str) -> dict[str, list[str]]:
    if not isinstance(value, Mapping) or set(value) != set(_OBJECT_KINDS):
        raise _typed("OBJECT_CLOSURE_DRIFT", f"{label} fields are not exact")
    result: dict[str, list[str]] = {}
    for kind in _OBJECT_KINDS:
        result[kind] = list(
            _sorted_unique_strings(value.get(kind), label=f"{label}.{kind}")
        )
    return result


def _object_ref(kind: str, ref: str) -> str:
    return f"{kind}/{ref}"


def _object_directory(release_root: Path, kind: str, ref: str) -> Path:
    fragment = _safe_ref(ref, label=f"desiredRefs.{kind}")
    root = release_root / "payload" / "objects" / kind
    candidate = root / fragment
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (FileNotFoundError, ValueError) as exc:
        raise _typed(
            "OBJECT_CLOSURE_DRIFT", f"missing canonical object {kind}/{ref}"
        ) from exc
    if not resolved.is_dir():
        raise _typed(
            "OBJECT_CLOSURE_DRIFT", f"canonical object is not a directory: {kind}/{ref}"
        )
    return resolved


def _relative_output(path: Path, *, output_root: Path) -> str:
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise _typed("ROOT_DRIFT", "evidence path escaped output root") from exc


def _expected_evidence(
    *,
    release_root: Path,
    output_root: Path,
    desired_refs: Mapping[str, Sequence[str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    reviews: list[dict[str, str]] = []
    rights: list[dict[str, str]] = []
    for kind in _OBJECT_KINDS:
        for ref in desired_refs[kind]:
            object_root = _object_directory(release_root, kind, ref)
            object_ref = _object_ref(kind, ref)
            if kind in {"entities", "posts"}:
                for filename in ("attestation.json", "evidence_index.json"):
                    path = object_root / filename
                    if path.is_symlink() or not path.is_file():
                        raise _typed(
                            "REVIEW_CLOSURE_DRIFT",
                            f"{object_ref} is missing {filename}",
                        )
                    reviews.append(
                        {
                            "objectRef": object_ref,
                            "ref": _relative_output(path, output_root=output_root),
                            "sha256": file_digest(path),
                        }
                    )
                rights_path = object_root / "rights.json"
                if rights_path.is_symlink() or not rights_path.is_file():
                    raise _typed(
                        "RIGHTS_CLOSURE_DRIFT",
                        f"{object_ref} is missing rights.json",
                    )
                rights.append(
                    {
                        "objectRef": object_ref,
                        "ref": _relative_output(rights_path, output_root=output_root),
                        "sha256": file_digest(rights_path),
                    }
                )
            snapshot_root = object_root / "rights_snapshots"
            if snapshot_root.is_dir():
                for path in sorted(snapshot_root.glob("*.json")):
                    if path.is_symlink():
                        raise _typed(
                            "ROOT_DRIFT", f"{object_ref} rights snapshot is a symlink"
                        )
                    rights.append(
                        {
                            "objectRef": object_ref,
                            "ref": _relative_output(path, output_root=output_root),
                            "sha256": file_digest(path),
                        }
                    )
    reviews.sort(key=lambda item: (item["objectRef"], item["ref"]))
    rights.sort(key=lambda item: (item["objectRef"], item["ref"]))
    return reviews, rights


def _validate_evidence_rows(
    value: object,
    *,
    expected: list[dict[str, str]],
    output_root: Path,
    label: str,
) -> list[dict[str, str]]:
    if value != expected:
        raise _typed(f"{label.upper()}_CLOSURE_DRIFT", f"{label} evidence is not exact")
    for index, row in enumerate(expected):
        _validate_file_evidence(
            {"ref": row["ref"], "sha256": row["sha256"]},
            output_root=output_root,
            label=f"{label}Evidence[{index}]",
        )
    return expected


def _media_assets(
    value: object,
    *,
    release_root: Path,
    desired_refs: Mapping[str, Sequence[str]],
    rights_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        raise _typed("MEDIA_CLOSURE_DRIFT", "media manifest must contain assets")
    owner_closure = {
        _object_ref(kind, ref) for kind in _OBJECT_KINDS for ref in desired_refs[kind]
    }
    rights_refs = {str(row["ref"]).split("/payload/", 1)[-1] for row in rights_rows}
    normalized: list[dict[str, object]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise _typed("MEDIA_CLOSURE_DRIFT", f"media asset {index} is invalid")
        owner_refs = tuple(str(item) for item in row.get("ownerRefs") or [])
        snapshot_refs = tuple(str(item) for item in row.get("rightsSnapshotRefs") or [])
        if (
            not owner_refs
            or owner_refs != tuple(sorted(set(owner_refs)))
            or not set(owner_refs).issubset(owner_closure)
        ):
            raise _typed(
                "MEDIA_CLOSURE_DRIFT", f"media asset {index} owner closure drifted"
            )
        if (
            not snapshot_refs
            or snapshot_refs != tuple(sorted(set(snapshot_refs)))
            or not set(snapshot_refs).issubset(rights_refs)
        ):
            raise _typed(
                "RIGHTS_CLOSURE_DRIFT", f"media asset {index} rights closure drifted"
            )
        public_slice = _safe_ref(
            row.get("publicSliceKey"), label=f"mediaAssets[{index}].publicSliceKey"
        )
        media_path = release_root / "payload" / public_slice
        if media_path.is_symlink() or not media_path.is_file():
            raise _typed(
                "MEDIA_CLOSURE_DRIFT", f"media asset {index} bytes are missing"
            )
        normalized_row: dict[str, object] = {
            "assetId": str(row.get("assetId") or ""),
            "kind": str(row.get("kind") or ""),
            "contentType": str(row.get("contentType") or ""),
            "bytes": int(row.get("bytes") or 0),
            "sha256": str(row.get("sha256") or ""),
            "publicSliceKey": public_slice.as_posix(),
            "version": int(row.get("version") or 0),
            "ownerRefs": list(owner_refs),
            "rightsSnapshotRefs": list(snapshot_refs),
        }
        if (
            any(
                not str(normalized_row[key])
                for key in ("assetId", "kind", "contentType")
            )
            or not _is_sha256(str(normalized_row["sha256"]))
            or normalized_row["bytes"] != media_path.stat().st_size
            or normalized_row["bytes"] <= 0
            or normalized_row["version"] <= 0
            or normalized_row["sha256"] != file_digest(media_path)
        ):
            raise _typed("MEDIA_CLOSURE_DRIFT", f"media asset {index} identity drifted")
        normalized.append(normalized_row)
    normalized.sort(key=lambda item: str(item["assetId"]))
    asset_ids = tuple(str(row["assetId"]) for row in normalized)
    if asset_ids != tuple(sorted(set(asset_ids))):
        raise _typed("MEDIA_CLOSURE_DRIFT", "media assetIds must be unique")
    return normalized


def validate_reviewed_closure_adoption_ref(
    value: object,
    *,
    output_root: Path,
) -> ReviewedClosureAdoptionRef:
    """Validate exact release bytes plus object/media/review/rights provenance."""
    try:
        assert_valid(
            value,
            "execution",
            "reviewed_closure_adoption_ref",
            label="reviewed closure adoption ref",
        )
    except ValueError as exc:
        raise _typed("REF_SCHEMA_INVALID", str(exc)) from exc
    if not isinstance(value, Mapping):
        raise _typed("REF_SCHEMA_INVALID", "adoption ref must be an object")
    document = dict(value)
    _validate_digest_field(document, "adoptionRefDigest")
    _timestamp(document.get("recordedAt"), label="adoptionRef.recordedAt")
    identity = ReleaseIdentityTuple.from_document(
        document.get("sourceReleaseIdentity"), label="sourceReleaseIdentity"
    )
    expected_root_ref = f"data/releases/{identity.release_id}"
    if document.get("sourceReleaseRootRef") != expected_root_ref:
        raise _typed("ROOT_DRIFT", "source release root is not canonical")
    release_root = _resolve_path(
        expected_root_ref,
        output_root=output_root,
        label="sourceReleaseRootRef",
        kind="directory",
    )
    if payload_digest(release_root) != identity.payload_sha256:
        raise _typed("PAYLOAD_DRIFT", "source release payload digest drifted")
    if object_closure_digest(release_root) != identity.canonical_merkle:
        raise _typed("OBJECT_CLOSURE_DRIFT", "source object Merkle drifted")

    source_evidence = document.get("sourceEvidence")
    if not isinstance(source_evidence, Mapping):
        raise _typed("EVIDENCE_INVALID", "sourceEvidence must be an object")
    evidence_documents: dict[str, dict[str, Any]] = {}
    for field, suffix in _SOURCE_EVIDENCE_PATHS.items():
        expected_ref = f"{expected_root_ref}/{suffix}"
        path = _validate_file_evidence(
            source_evidence.get(field),
            output_root=output_root,
            label=f"sourceEvidence.{field}",
            expected_ref=expected_ref,
        )
        evidence_documents[field] = _read_object(path, label=field)
    attestation_binding = source_evidence["releaseAttestation"]
    if attestation_binding.get("sha256") != identity.attestation_file_sha256:
        raise _typed("IDENTITY_DRIFT", "attestation file identity drifted")
    attestation = evidence_documents["releaseAttestation"]
    header = evidence_documents["releaseHeader"]
    for candidate, label in ((attestation, "attestation"), (header, "release header")):
        if (
            candidate.get("releaseId") != identity.release_id
            or candidate.get("canonicalMerkle") != identity.canonical_merkle
        ):
            raise _typed("IDENTITY_DRIFT", f"{label} release identity drifted")
    if attestation.get("payloadSha256") != identity.payload_sha256:
        raise _typed("IDENTITY_DRIFT", "attestation payload identity drifted")

    incident_binding = document.get("identityIncident")
    if not isinstance(incident_binding, Mapping) or set(incident_binding) != {
        "ref",
        "fileSha256",
        "receiptDigest",
    }:
        raise _typed("INCIDENT_INVALID", "identityIncident binding is invalid")
    incident_path = _resolve_path(
        incident_binding.get("ref"),
        output_root=output_root,
        label="identityIncident.ref",
        kind="file",
    )
    if file_digest(incident_path) != incident_binding.get("fileSha256"):
        raise _typed("DIGEST_DRIFT", "identity incident file digest drifted")
    incident = validate_release_identity_incident(
        _read_object(incident_path, label="identity incident"),
        output_root=output_root,
    )
    if (
        incident.release_id != identity.release_id
        or incident.receipt_digest != incident_binding.get("receiptDigest")
        or identity not in incident.observed_identities
    ):
        raise _typed(
            "INCIDENT_INVALID", "identity incident does not bind the source tuple"
        )

    desired_state = evidence_documents["desiredState"]
    object_index = evidence_documents["objectIndex"]
    if desired_state.get("releaseId") != identity.release_id or set(object_index) != {
        "schema",
        *_OBJECT_KINDS,
    }:
        raise _typed("OBJECT_CLOSURE_DRIFT", "desired state/object index shape drifted")
    desired_refs = _desired_refs(
        desired_state.get("desiredRefs"), label="desiredState.desiredRefs"
    )
    indexed_refs = _desired_refs(
        {kind: object_index.get(kind) for kind in _OBJECT_KINDS},
        label="objectIndex",
    )
    declared_refs = _desired_refs(
        document.get("desiredRefs"), label="adoptionRef.desiredRefs"
    )
    if desired_refs != indexed_refs or desired_refs != declared_refs:
        raise _typed("OBJECT_CLOSURE_DRIFT", "desired state and object index differ")
    post_carriers = {ref.split("/", 1)[0] for ref in desired_refs["posts"]}
    if post_carriers != {"article", "image", "video"}:
        raise _typed(
            "OBJECT_CLOSURE_DRIFT", "source release lacks the three post carriers"
        )

    reviews, rights = _expected_evidence(
        release_root=release_root,
        output_root=output_root,
        desired_refs=desired_refs,
    )
    _validate_evidence_rows(
        document.get("reviewEvidence"),
        expected=reviews,
        output_root=output_root,
        label="review",
    )
    _validate_evidence_rows(
        document.get("rightsEvidence"),
        expected=rights,
        output_root=output_root,
        label="rights",
    )
    media_manifest = evidence_documents["mediaManifest"]
    if media_manifest.get("releaseId") != identity.release_id:
        raise _typed("MEDIA_CLOSURE_DRIFT", "media manifest releaseId drifted")
    media_assets = _media_assets(
        media_manifest.get("assets"),
        release_root=release_root,
        desired_refs=desired_refs,
        rights_rows=rights,
    )
    if document.get("mediaAssets") != media_assets:
        raise _typed("MEDIA_CLOSURE_DRIFT", "adoption media identities are not exact")

    executions = _sorted_unique_strings(
        header.get("executionIds"), label="releaseHeader.executionIds"
    )
    source_documents = _source_digests(
        header.get("sourceDigests"), label="releaseHeader.sourceDigests"
    )
    upstream = {
        "executionIds": list(executions),
        "sourceDigests": [dict(row) for row in source_documents],
    }
    if document.get("upstreamProvenance") != upstream:
        raise _typed(
            "UPSTREAM_INVALID", "upstream provenance differs from release header"
        )

    expected_digests = {
        "objects": identity.canonical_merkle,
        "media": canonical_digest(media_assets),
        "review": canonical_digest(reviews),
        "rights": canonical_digest(rights),
        "upstream": canonical_digest(upstream),
    }
    if document.get("closureDigests") != expected_digests:
        raise _typed("DIGEST_DRIFT", "closureDigests do not match exact evidence")
    return ReviewedClosureAdoptionRef(
        adoption_id=str(document.get("adoptionId") or ""),
        source_release_identity=identity,
        source_release_root=release_root,
        upstream_execution_ids=executions,
        upstream_source_digests=tuple(str(row["digest"]) for row in source_documents),
        closure_digests=tuple(sorted(expected_digests.items())),
        adoption_ref_digest=str(document["adoptionRefDigest"]),
    )


def validate_reviewed_closure_adoption_receipt(
    value: object,
    *,
    output_root: Path,
) -> ReviewedClosureAdoptionReceipt:
    """Validate a four-lane receipt against its exact adoption reference."""
    try:
        assert_valid(
            value,
            "execution",
            "reviewed_closure_adoption_receipt",
            label="reviewed closure adoption receipt",
        )
    except ValueError as exc:
        raise _typed("RECEIPT_SCHEMA_INVALID", str(exc)) from exc
    if not isinstance(value, Mapping):
        raise _typed("RECEIPT_SCHEMA_INVALID", "adoption receipt must be an object")
    document = dict(value)
    _validate_digest_field(document, "receiptDigest")
    _timestamp(document.get("recordedAt"), label="adoptionReceipt.recordedAt")
    binding = document.get("adoptionRef")
    if not isinstance(binding, Mapping) or set(binding) != {
        "ref",
        "fileSha256",
        "adoptionRefDigest",
    }:
        raise _typed("REF_SCHEMA_INVALID", "adoptionRef binding is invalid")
    ref_path = _resolve_path(
        binding.get("ref"),
        output_root=output_root,
        label="adoptionRef.ref",
        kind="file",
    )
    if file_digest(ref_path) != binding.get("fileSha256"):
        raise _typed("DIGEST_DRIFT", "adoption ref file digest drifted")
    ref_document = _read_object(ref_path, label="reviewed closure adoption ref")
    adoption_ref = validate_reviewed_closure_adoption_ref(
        ref_document,
        output_root=output_root,
    )
    if binding.get("adoptionRefDigest") != adoption_ref.adoption_ref_digest:
        raise _typed("DIGEST_DRIFT", "adoptionRefDigest binding drifted")
    if (
        document.get("adoptionId") != adoption_ref.adoption_id
        or document.get("sourceReleaseIdentity")
        != adoption_ref.source_release_identity.to_document()
        or document.get("closureDigests") != dict(adoption_ref.closure_digests)
    ):
        raise _typed("IDENTITY_DRIFT", "receipt differs from adoption ref identity")
    upstream = ref_document["upstreamProvenance"]
    if document.get("upstreamProvenance") != upstream:
        raise _typed("UPSTREAM_INVALID", "receipt upstream provenance drifted")

    target = document.get("targetSourceIdentity")
    if not isinstance(target, Mapping):
        raise _typed("TARGET_IDENTITY_INVALID", "targetSourceIdentity is invalid")
    try:
        target_source = SourceDigest.from_document(target.get("sourceDigest"))
        expected_revision = content_source_revision(
            source_digest=target_source.digest,
            entity_catalog_digest=str(target.get("entityCatalogDigest") or ""),
        )
    except SourceDigestError as exc:
        raise _typed("TARGET_IDENTITY_INVALID", str(exc)) from exc
    if target.get("sourceRevision") != expected_revision:
        raise _typed("TARGET_IDENTITY_INVALID", "target sourceRevision is not derived")
    if target_source.digest in adoption_ref.upstream_source_digests:
        raise _typed(
            "TARGET_IDENTITY_INVALID",
            "target sourceDigest must identify the new adoption execution",
        )

    source_refs = ref_document["desiredRefs"]
    expected_lanes = {
        "homepage": [f"entities/{ref}" for ref in source_refs["entities"]],
        "article": [
            f"posts/{ref}" for ref in source_refs["posts"] if ref.startswith("article/")
        ],
        "image": [
            f"posts/{ref}" for ref in source_refs["posts"] if ref.startswith("image/")
        ],
        "video": [
            f"posts/{ref}" for ref in source_refs["posts"] if ref.startswith("video/")
        ],
    }
    lane_rows = document.get("laneExecutions")
    if not isinstance(lane_rows, list) or len(lane_rows) != len(_CARRIERS):
        raise _typed("LANE_CLOSURE_DRIFT", "exactly four lane executions are required")
    observed_carriers: list[str] = []
    lane_execution_ids: list[str] = []
    for index, row in enumerate(lane_rows):
        if not isinstance(row, Mapping):
            raise _typed("LANE_CLOSURE_DRIFT", f"laneExecutions[{index}] is invalid")
        carrier = str(row.get("carrier") or "")
        observed_carriers.append(carrier)
        execution_id = str(row.get("executionId") or "")
        lane_execution_ids.append(execution_id)
        refs = row.get("adoptedObjectRefs")
        if refs != expected_lanes.get(carrier):
            raise _typed(
                "LANE_CLOSURE_DRIFT", f"{carrier or index} object closure drifted"
            )
    if tuple(observed_carriers) != _CARRIERS:
        raise _typed("LANE_CLOSURE_DRIFT", "lane executions are not in canonical order")
    if (
        any(not item for item in lane_execution_ids)
        or len(set(lane_execution_ids)) != len(_CARRIERS)
        or set(lane_execution_ids).intersection(adoption_ref.upstream_execution_ids)
    ):
        raise _typed("LANE_CLOSURE_DRIFT", "lane execution identity is invalid")
    expected_shared = [
        *[f"creators/{ref}" for ref in source_refs["creators"]],
        *[f"tags/{ref}" for ref in source_refs["tags"]],
    ]
    if document.get("sharedObjectRefs") != expected_shared:
        raise _typed("OBJECT_CLOSURE_DRIFT", "shared object closure drifted")
    return ReviewedClosureAdoptionReceipt(
        adoption_id=adoption_ref.adoption_id,
        source_release_identity=adoption_ref.source_release_identity,
        target_source_revision=expected_revision,
        target_source_digest=target_source.digest,
        lane_execution_ids=tuple(lane_execution_ids),
        receipt_digest=str(document["receiptDigest"]),
    )


__all__ = [
    "ReleaseIdentityIncident",
    "ReleaseIdentityTuple",
    "ReviewedClosureAdoptionError",
    "ReviewedClosureAdoptionReceipt",
    "ReviewedClosureAdoptionRef",
    "canonical_digest",
    "file_digest",
    "validate_release_identity_incident",
    "validate_reviewed_closure_adoption_receipt",
    "validate_reviewed_closure_adoption_ref",
]
