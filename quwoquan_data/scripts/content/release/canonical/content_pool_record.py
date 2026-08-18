"""Append-only admission records for author, homepage and content pool objects."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_source_identity import (
    validate_object_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_bytes,
    _digest_file,
    _files,
    _json_bytes,
    _read_json,
    _safe_rel,
    _write_json,
)
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)
from content.release.canonical.pool_record_history import (
    POOL_RECORD_SCHEMA,
    PoolRecordExclusion,
    PoolRecordHistory,
    _validated_pool_record,
    iter_pool_records,
    pool_source_identity_digest,
    read_pool_record_history,
)


def stable_content_id(source_manifest: Mapping[str, Any], canonical_ref: str) -> str:
    """Return the explicit immutable content identity; never infer implicit IDs."""

    explicit = str(source_manifest.get("contentId") or "").strip()
    if not explicit:
        raise ObjectTransactionError(
            "DATA.POOL.IDENTITY_INVALID: "
            f"{canonical_ref} lacks explicit manifest.contentId"
        )
    return explicit


def pool_payload_digest(object_root: Path) -> str:
    """Digest immutable object bytes while excluding append-only pool records.

    Media bytes stay outside the digest because canonical publish records media
    by content digest and never copies the bytes alongside the object, so an
    execution package that still holds them and the canonical object that never
    receives them must agree on one digest.  The closure over media is kept by
    ``asset.refs.json``, which carries every asset's own sha256 and is itself
    digested here.
    """

    rows = []
    for path in _files(object_root):
        relative = path.relative_to(object_root)
        if relative.parts and relative.parts[0] in {"_pool", "assets"}:
            continue
        rows.append(
            {
                "path": relative.as_posix(),
                "sha256": _digest_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return _digest_bytes(_json_bytes(rows))


def _pool_record_path(object_root: Path, record_sequence: int) -> Path:
    return object_root / "_pool" / "versions" / f"{record_sequence}.json"


def _inline_author_record(object_root: Path) -> dict[str, Any] | None:
    path = object_root / "profile.json"
    if not path.is_file():
        return None
    document = _read_json(path)
    admission = document.get("admission")
    version = document.get("version")
    author_id = str(
        document.get("authorId") or document.get("creatorId") or ""
    ).strip()
    if (
        not isinstance(admission, Mapping)
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
        or not author_id
    ):
        return None
    return _validated_pool_record(
        {
            "schema": POOL_RECORD_SCHEMA,
            "objectType": "author",
            "objectId": author_id,
            "objectRef": object_root.name,
            "recordSequence": 1,
            "contentVersion": version,
            "status": str(document.get("status") or "active"),
            "processResult": str(admission.get("processResult") or "failed"),
            "qualityResult": str(admission.get("qualityResult") or "failed"),
            "eligibilityResult": "passed",
            "usageScope": None,
            "evidenceRef": str(admission.get("evidenceRef") or ""),
            "evidenceDigest": str(admission.get("evidenceDigest") or ""),
            "payloadDigest": pool_payload_digest(object_root),
        },
        object_type="author",
    )


def latest_pool_record(object_root: Path, object_type: str | None = None) -> dict[str, Any] | None:
    """Return the latest explicit sidecar; inline manifest admission is not pool truth."""

    records = iter_pool_records(object_root, object_type=object_type)
    if not records:
        return (
            _inline_author_record(object_root)
            if object_type == "author"
            else None
        )
    record = records[-1]
    if (
        record.get("objectType") != "author"
        and record.get("payloadDigest") != pool_payload_digest(object_root)
    ):
        raise ObjectTransactionError("DATA.POOL.PAYLOAD_DIGEST_DRIFT")
    evidence = object_root / _safe_rel(
        str(record.get("evidenceRef") or ""), label="poolRecord.evidenceRef"
    )
    if record.get("objectType") == "author":
        return record
    if (
        evidence.is_symlink()
        or not evidence.is_file()
        or _digest_file(evidence) != record.get("evidenceDigest")
    ):
        raise ObjectTransactionError("DATA.POOL.EVIDENCE_DIGEST_DRIFT")
    return record


def is_pool_record_admitted(record: Mapping[str, Any] | None) -> bool:
    if not isinstance(record, Mapping):
        return False
    return (
        record.get("status") == "active"
        and record.get("processResult") == "completed"
        and record.get("qualityResult") == "passed"
        and record.get("eligibilityResult") == "passed"
        and (
            record.get("objectType") == "author"
            or record.get("usageScope") in {"research", "commercial"}
        )
    )


def preflight_pool_record_append(
    *, object_root: Path, record: Mapping[str, Any]
) -> tuple[str, Path]:
    validated = _validated_pool_record(record)
    record_sequence = int(validated["recordSequence"])
    target = _pool_record_path(object_root, record_sequence)
    if target.is_file():
        if _read_json(target) == validated:
            return "replayed", target
        raise ObjectTransactionError(
            "DATA.POOL.VERSION_CONFLICT: "
            f"objectId={validated['objectId']} recordSequence={record_sequence}"
        )
    records = iter_pool_records(object_root, object_type=str(validated["objectType"]))
    if records and record_sequence != int(records[-1]["recordSequence"]) + 1:
        raise ObjectTransactionError(
            "DATA.POOL.VERSION_GAP: "
            f"objectId={validated['objectId']} "
            f"expected={int(records[-1]['recordSequence']) + 1} "
            f"actual={record_sequence}"
        )
    return "appended", target


def append_pool_record(
    *, object_root: Path, record: Mapping[str, Any]
) -> tuple[str, Path]:
    """Append one version. Same record replays; same version drift conflicts."""
    status, target = preflight_pool_record_append(object_root=object_root, record=record)
    if status == "replayed":
        return status, target
    validated = _validated_pool_record(record)
    _write_json(target, validated)
    return "appended", target


def build_canonical_pool_record(
    *,
    object_root: Path,
    object_type: str,
    object_ref: str,
) -> dict[str, Any]:
    """Freeze one canonical object's explicit identity and delivery closure."""

    if object_type not in {"homepage", "content"}:
        raise ObjectTransactionError("DATA.POOL.RECORD_OBJECT_TYPE_INVALID")
    manifest = _read_json(object_root / "manifest.json")
    object_id = str(
        manifest.get("entityId" if object_type == "homepage" else "contentId")
        or ""
    ).strip()
    version = manifest.get("version")
    if (
        not object_id
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID")
    identity = validate_object_source_identity(manifest)
    attribution = manifest.get("sourceAttribution")
    if not source_attribution_complete({"sourceAttribution": attribution}):
        raise ObjectTransactionError("DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE")
    admission = manifest.get("admission")
    if not isinstance(admission, Mapping):
        raise ObjectTransactionError("DATA.POOL.ADMISSION_MISSING")
    evidence_ref = str(admission.get("evidenceRef") or "").strip()
    evidence = object_root / _safe_rel(
        evidence_ref, label="poolRecord.evidenceRef"
    )
    evidence_digest = str(admission.get("evidenceDigest") or "").strip()
    if (
        evidence.is_symlink()
        or not evidence.is_file()
        or _digest_file(evidence) != evidence_digest
    ):
        raise ObjectTransactionError("DATA.POOL.EVIDENCE_DIGEST_DRIFT")
    payload_digest = pool_payload_digest(object_root)
    records = iter_pool_records(object_root, object_type=object_type)
    return _validated_pool_record(
        {
            "schema": POOL_RECORD_SCHEMA,
            "objectType": object_type,
            "objectId": object_id,
            "objectRef": object_ref,
            "recordSequence": (
                int(records[-1]["recordSequence"]) + 1 if records else 1
            ),
            "contentVersion": version,
            "status": str(manifest.get("status") or "active"),
            "processResult": str(admission.get("processResult") or "failed"),
            "qualityResult": str(admission.get("qualityResult") or "failed"),
            "eligibilityResult": "passed",
            "usageScope": str(admission.get("usageScope") or "").strip() or None,
            "evidenceRef": evidence_ref,
            "evidenceDigest": evidence_digest,
            "payloadDigest": payload_digest,
            "canonicalObjectDigest": payload_digest,
            "sourceIdentity": identity,
            "sourceAttribution": attribution,
        },
        object_type=object_type,
    )


def _pool_identity_rows(
    object_root: Path,
    *,
    object_ref: str,
) -> list[tuple[str, int, bool]]:
    """Read collision identity without promoting a retired record to admission."""

    rows: list[tuple[str, int, bool]] = []
    versions_root = object_root / "_pool/versions"
    if not versions_root.is_dir():
        return rows
    for record_path in sorted(versions_root.glob("*.json")):
        if not record_path.is_file() or not record_path.stem.isdigit():
            raise ObjectTransactionError("DATA.POOL.RECORD_SEQUENCE_CONFLICT")
        physical_sequence = int(record_path.stem)
        raw = _read_json(record_path)
        object_id = str(raw.get("objectId") or "").strip()
        if (
            raw.get("schema") != POOL_RECORD_SCHEMA
            or raw.get("objectType") != "content"
            or not object_id
            or raw.get("objectRef") != object_ref
        ):
            raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID")
        if "recordSequence" in raw or "contentVersion" in raw:
            record_sequence = raw.get("recordSequence")
            content_version = raw.get("contentVersion")
            if (
                not isinstance(record_sequence, int)
                or isinstance(record_sequence, bool)
                or record_sequence != physical_sequence
                or not isinstance(content_version, int)
                or isinstance(content_version, bool)
                or content_version < 1
            ):
                raise ObjectTransactionError(
                    "DATA.POOL.RECORD_VERSION_INVALID"
                )
            try:
                _validated_pool_record(raw, object_type="content")
                retired = False
            except ObjectTransactionError as exc:
                retired = str(exc) in {
                    "DATA.POOL.SOURCE_IDENTITY_INVALID",
                    "DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE",
                    "DATA.POOL.CANONICAL_DIGEST_DRIFT",
                }
                if not retired:
                    raise
        else:
            content_version = raw.get("version")
            if (
                not isinstance(content_version, int)
                or isinstance(content_version, bool)
                or content_version != physical_sequence
            ):
                raise ObjectTransactionError(
                    "DATA.POOL.RECORD_SEQUENCE_MISSING"
                )
            retired = True
        rows.append((object_id, int(content_version), retired))
    return rows


def _known_versions(publish_root: Path, content_id: str) -> list[int]:
    versions: list[int] = []
    for path in sorted((publish_root / "posts").rglob("manifest.json")):
        document = _read_json(path)
        object_ref = path.parent.relative_to(publish_root / "posts").as_posix()
        identity_rows = _pool_identity_rows(
            path.parent,
            object_ref=object_ref,
        )
        manifest_content_id = str(document.get("contentId") or "").strip()
        manifest_version = document.get("version")
        has_content_id = bool(manifest_content_id)
        has_version = "version" in document
        if has_content_id != has_version:
            raise ObjectTransactionError(
                "DATA.POOL.IDENTITY_INVALID: manifest contentId/version must coexist"
            )
        if not has_content_id:
            if identity_rows:
                if not all(row[2] for row in identity_rows):
                    raise ObjectTransactionError(
                        "DATA.POOL.IDENTITY_INVALID: modern pool record lacks manifest identity"
                    )
                retired_pairs = {(row[0], row[1]) for row in identity_rows}
                if len(retired_pairs) != 1:
                    raise ObjectTransactionError(
                        "DATA.POOL.IDENTITY_INVALID: pool record identity drift"
                    )
                retired_content_id, retired_version = next(iter(retired_pairs))
                if retired_content_id == content_id:
                    versions.append(retired_version)
                continue
            continue
        if (
            not isinstance(manifest_version, int)
            or isinstance(manifest_version, bool)
            or manifest_version < 1
        ):
            raise ObjectTransactionError(
                "DATA.POOL.IDENTITY_INVALID: manifest.version must be positive"
            )
        if identity_rows and any(
            row[:2] != (manifest_content_id, manifest_version)
            for row in identity_rows
        ):
            raise ObjectTransactionError(
                "DATA.POOL.IDENTITY_INVALID: manifest/pool record identity drift"
            )
        if manifest_content_id == content_id:
            versions.append(manifest_version)
    if len(versions) != len(set(versions)):
        raise ObjectTransactionError(
            f"content pool contains duplicate versions: {content_id}"
        )
    return sorted(versions)


def _commercial_proof_closed(
    source_manifest: Mapping[str, Any], rights_rows: list[dict[str, Any]]
) -> bool:
    attribution = source_manifest.get("sourceAttribution")
    if not isinstance(attribution, Mapping):
        return False
    if (
        attribution.get("publicationAdmission") != "commercial_release"
        or attribution.get("commercialAuthorizationStatus") != "verified"
        or not str(attribution.get("authorizationProofUrl") or "").startswith("https://")
        or not str(attribution.get("termsUrl") or "").startswith("https://")
    ):
        return False
    return all(
        row.get("distributionDecision") == "commercial_allowed"
        and row.get("rightsAuditStatus") == "verified"
        and str(row.get("authorizationProof") or "").startswith("https://")
        and str(row.get("licenseUrl") or "").startswith("https://")
        and bool(str(row.get("author") or "").strip())
        and bool(str(row.get("licenseName") or "").strip())
        for row in rights_rows
    )


def pool_usage_scope(
    source_manifest: Mapping[str, Any], rights_rows: list[dict[str, Any]]
) -> str:
    """Derive pool eligibility only from per-object attribution and rights facts."""

    return (
        "commercial"
        if _commercial_proof_closed(source_manifest, rights_rows)
        else "research"
    )


def plan_content_pool_identity(
    *,
    source_manifest: Mapping[str, Any],
    canonical_ref: str,
    publish_root: Path,
) -> dict[str, Any]:
    """Plan the next stable Post identity before delivery mutates canonical pool."""

    content_id = stable_content_id(source_manifest, canonical_ref)
    requested_version = source_manifest.get("version")
    if (
        not isinstance(requested_version, int)
        or isinstance(requested_version, bool)
        or requested_version < 1
    ):
        raise ObjectTransactionError(
            "DATA.POOL.IDENTITY_INVALID: manifest.version must be explicit"
        )
    _known_versions(publish_root, content_id)
    return {"contentId": content_id, "version": requested_version}


def build_content_pool_fields(
    *,
    source_manifest: Mapping[str, Any],
    canonical_ref: str,
    source_task_id: str,
    attestation_path: Path,
    publish_root: Path,
    rights_rows: list[dict[str, Any]],
    reserved_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Build minimal explicit fields for a newly generated Post."""

    planned = plan_content_pool_identity(
        source_manifest=source_manifest,
        canonical_ref=canonical_ref,
        publish_root=publish_root,
    )
    content_id = str(reserved_identity.get("contentId") or "").strip()
    version = reserved_identity.get("version")
    if content_id != planned["contentId"]:
        raise ObjectTransactionError("pool delivery reserved contentId drift")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ObjectTransactionError("pool delivery reserved version is invalid")
    requested_version = source_manifest.get("version")
    if requested_version is not None and requested_version != version:
        raise ObjectTransactionError("pool delivery reserved version drift")
    known_versions = _known_versions(publish_root, content_id)
    if version in known_versions:
        raise ObjectTransactionError(
            "DATA.POOL.VERSION_CONFLICT: "
            f"contentId={content_id} version={version} already exists"
        )
    if known_versions and version != known_versions[-1] + 1:
        raise ObjectTransactionError(
            "DATA.POOL.VERSION_GAP: "
            f"contentId={content_id} expected={known_versions[-1] + 1} actual={version}"
        )
    usage_scope = pool_usage_scope(source_manifest, rights_rows)
    variant_purpose = str(source_manifest.get("variantPurpose") or "original").strip()
    if variant_purpose not in {"original", "commercial_variant"}:
        raise ObjectTransactionError(
            f"content variantPurpose is invalid: {variant_purpose!r}"
        )
    if variant_purpose == "commercial_variant" and usage_scope != "commercial":
        raise ObjectTransactionError(
            "DATA.POOL.COMMERCIAL_VARIANT_NOT_ADMITTED: commercial_variant must be commercial"
        )
    return {
        "contentId": content_id,
        "version": version,
        "sourceType": "data",
        "variantPurpose": variant_purpose,
        "admission": {
            "processResult": "completed",
            "qualityResult": "passed",
            "usageScope": usage_scope,
            "evidenceRef": "attestation.json",
            "evidenceDigest": _digest_file(attestation_path),
        },
        "status": "active",
        "sourceTaskId": source_task_id,
    }


__all__ = [
    "POOL_RECORD_SCHEMA",
    "PoolRecordExclusion",
    "PoolRecordHistory",
    "append_pool_record",
    "build_canonical_pool_record",
    "build_content_pool_fields",
    "is_pool_record_admitted",
    "iter_pool_records",
    "latest_pool_record",
    "plan_content_pool_identity",
    "pool_usage_scope",
    "pool_payload_digest",
    "pool_source_identity_digest",
    "preflight_pool_record_append",
    "read_pool_record_history",
    "stable_content_id",
]
