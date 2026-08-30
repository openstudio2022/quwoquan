"""Project canonical pool owner facts into the release-consumer whitelist.

``ContentPoolHandoffQuery`` is an in-memory read model.  It has no repository,
checkpoint, command, or writer.  The canonical object package and its latest
append-only pool record remain the only persistent facts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import (
    is_pool_record_admitted,
    latest_pool_record,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)
from core.media_asset_url import is_cas_media_object_key
from core.schema import assert_valid

_SCHEMA = "quwoquan_data.content_pool_handoff_query"
_PROJECTOR_VERSION = "content_pool_handoff_v1"
_SPEC_REF = (
    "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/"
    "multi-carrier-release/spec.md#req-008"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTENT_TYPES = ("article", "image", "video")


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ContentLibraryBinding:
    asset_id: str
    object_key: str
    sha256: str

    def as_document(self) -> dict[str, str]:
        return {
            "assetId": self.asset_id,
            "objectKey": self.object_key,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class ContentPoolHandoffQuery:
    object_type: str
    object_id: str
    object_ref: str
    carrier: str
    content_version: int
    record_sequence: int
    author_id: str | None
    status: str
    process_result: str
    quality_result: str
    eligibility_result: str
    usage_scope: str
    variant_purpose: str
    evidence_ref: str
    evidence_digest: str
    payload_digest: str
    canonical_object_digest: str
    selection_identity_digest: str
    canonical_object_ref: str
    manifest_ref: str
    pool_record_ref: str
    content_library_binding_ref: str | None
    content_library_binding_digest: str
    content_library_bindings: tuple[ContentLibraryBinding, ...]

    def as_document(self) -> dict[str, object]:
        identity: dict[str, object] = {
            "objectType": self.object_type,
            "objectId": self.object_id,
            "objectRef": self.object_ref,
            "carrier": self.carrier,
            "contentVersion": self.content_version,
            "recordSequence": self.record_sequence,
        }
        if self.author_id is not None:
            identity["authorId"] = self.author_id
        content_library: dict[str, object] = {
            "holder": "content_library",
            "bindingDigest": self.content_library_binding_digest,
            "bindings": [row.as_document() for row in self.content_library_bindings],
        }
        if self.content_library_binding_ref is not None:
            content_library["bindingRef"] = self.content_library_binding_ref
        document: dict[str, object] = {
            "schema": _SCHEMA,
            "projectorVersion": _PROJECTOR_VERSION,
            "specRef": _SPEC_REF,
            "identity": identity,
            "lifecycle": {"status": self.status},
            "admission": {
                "processResult": self.process_result,
                "qualityResult": self.quality_result,
                "eligibilityResult": self.eligibility_result,
                "rightsResult": "passed",
                "evidenceRef": self.evidence_ref,
                "evidenceDigest": self.evidence_digest,
            },
            "scope": {
                "usageScope": self.usage_scope,
                "variantPurpose": self.variant_purpose,
            },
            "digests": {
                "payloadDigest": self.payload_digest,
                "canonicalObjectDigest": self.canonical_object_digest,
                "selectionIdentityDigest": self.selection_identity_digest,
            },
            "refs": {
                "canonicalObjectRef": self.canonical_object_ref,
                "manifestRef": self.manifest_ref,
                "poolRecordRef": self.pool_record_ref,
            },
            "contentLibrary": content_library,
        }
        assert_valid(
            document,
            "release",
            "content_pool_handoff_query",
            label=f"ContentPoolHandoffQuery:{self.canonical_object_ref}",
        )
        return document


def _creator_ref(object_root: Path, manifest: Mapping[str, Any]) -> str:
    author_id = str(manifest.get("authorId") or "").strip()
    creator_refs_path = object_root / "creator.refs.json"
    if not author_id and creator_refs_path.is_file() and not creator_refs_path.is_symlink():
        raw_refs = _read_json(creator_refs_path).get("creatorRefs")
        if isinstance(raw_refs, list) and raw_refs:
            author_id = str(raw_refs[0] or "").strip()
    if not author_id:
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: authorId missing")
    return author_id


def _content_library_bindings(
    object_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[str | None, tuple[ContentLibraryBinding, ...], str]:
    declared_ref = str(manifest.get("assetRefsRef") or "").strip()
    if declared_ref:
        relative = _safe_rel(declared_ref, label="manifest.assetRefsRef")
        path = object_root / relative
        binding_ref: str | None = relative.as_posix()
        if path.is_symlink() or not path.is_file():
            raise ObjectTransactionError("DATA.POOL.CONTENT_LIBRARY_BINDING_MISSING")
    else:
        path = object_root / "asset.refs.json"
        binding_ref = "asset.refs.json" if path.is_file() and not path.is_symlink() else None
    if binding_ref is None:
        bindings: tuple[ContentLibraryBinding, ...] = ()
        return None, bindings, _canonical_digest([])

    document = _read_json(path)
    raw_bindings = document.get("assets")
    if not isinstance(raw_bindings, list):
        raise ObjectTransactionError("DATA.POOL.CONTENT_LIBRARY_BINDING_INVALID")
    rows: list[ContentLibraryBinding] = []
    seen_asset_ids: set[str] = set()
    for raw in raw_bindings:
        if not isinstance(raw, Mapping) or "publicSliceKey" in raw:
            raise ObjectTransactionError("DATA.POOL.CONTENT_LIBRARY_BINDING_INVALID")
        asset_id = str(raw.get("assetId") or "").strip()
        object_key = str(raw.get("objectKey") or "").strip()
        digest = str(raw.get("sha256") or "").strip()
        if (
            not asset_id
            or asset_id in seen_asset_ids
            or not is_cas_media_object_key(object_key)
            or not _DIGEST.fullmatch(digest)
            or f"/{digest[7:9]}/{digest[9:11]}/{digest[7:]}" not in object_key
        ):
            raise ObjectTransactionError("DATA.POOL.CONTENT_LIBRARY_BINDING_INVALID")
        seen_asset_ids.add(asset_id)
        rows.append(
            ContentLibraryBinding(
                asset_id=asset_id,
                object_key=object_key,
                sha256=digest,
            )
        )
    bindings = tuple(sorted(rows, key=lambda row: (row.asset_id, row.object_key)))
    return (
        binding_ref,
        bindings,
        _canonical_digest([row.as_document() for row in bindings]),
    )


def project_content_pool_handoff(
    *,
    publish_root: Path,
    object_type: str,
    object_ref: str,
) -> ContentPoolHandoffQuery | None:
    """Return one eligible projection, or ``None`` for retired/deleted facts."""

    normalized_type = str(object_type or "").strip()
    normalized_ref = str(object_ref or "").strip().removeprefix("/entity/")
    if normalized_type not in {"content", "homepage"} or not normalized_ref:
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID")
    kind = "posts" if normalized_type == "content" else "entities"
    object_root = Path(publish_root) / kind / normalized_ref
    manifest_path = object_root / "manifest.json"
    try:
        manifest = _read_json(manifest_path)
    except (OSError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            f"DATA.POOL.MANIFEST_INVALID: {kind}/{normalized_ref}: {exc}"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise ObjectTransactionError(
            f"DATA.POOL.MANIFEST_INVALID: {kind}/{normalized_ref}"
        )
    record = latest_pool_record(object_root, normalized_type)
    if not isinstance(record, Mapping):
        raise ObjectTransactionError(
            f"DATA.POOL.POST_NOT_ADMITTED: {kind}/{normalized_ref} admission=<missing>"
        )

    manifest_id_field = "contentId" if normalized_type == "content" else "entityId"
    object_id = str(record.get("objectId") or "").strip()
    manifest_id = str(manifest.get(manifest_id_field) or "").strip()
    content_version = record.get("contentVersion")
    manifest_version = manifest.get("version")
    record_sequence = record.get("recordSequence")
    if (
        not object_id
        or object_id != manifest_id
        or str(record.get("objectRef") or "").strip() != normalized_ref
        or isinstance(content_version, bool)
        or not isinstance(content_version, int)
        or content_version < 1
        or manifest_version != content_version
        or isinstance(record_sequence, bool)
        or not isinstance(record_sequence, int)
        or record_sequence < 1
    ):
        raise ObjectTransactionError(
            f"DATA.POOL.IDENTITY_INVALID: {kind}/{normalized_ref}"
        )
    if normalized_type == "homepage" and str(manifest.get("entityRef") or "").strip() != (
        f"/entity/{normalized_ref}"
    ):
        raise ObjectTransactionError(
            f"DATA.POOL.IDENTITY_INVALID: {kind}/{normalized_ref}"
        )

    status = str(record.get("status") or "").strip()
    if status in {"retired", "deleted"}:
        return None
    if not is_pool_record_admitted(record):
        if record.get("qualityResult") == "failed":
            raise ObjectTransactionError(
                f"DATA.POOL.QUALITY_FAILED: {kind}/{normalized_ref}"
            )
        raise ObjectTransactionError(
            f"DATA.POOL.ELIGIBILITY_FAILED: {kind}/{normalized_ref}"
        )
    if not source_attribution_complete(
        {"sourceAttribution": record.get("sourceAttribution")}
    ):
        raise ObjectTransactionError(
            f"DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE: {kind}/{normalized_ref}"
        )

    usage_scope = str(record.get("usageScope") or "").strip()
    if usage_scope not in {"research", "commercial"}:
        raise ObjectTransactionError(
            f"DATA.POOL.USAGE_SCOPE_INVALID: {kind}/{normalized_ref}"
        )
    if normalized_type == "content":
        carrier = str(manifest.get("contentType") or "").strip()
        if carrier not in _CONTENT_TYPES:
            raise ObjectTransactionError(
                f"DATA.POOL.IDENTITY_INVALID: {kind}/{normalized_ref} contentType"
            )
        author_id: str | None = _creator_ref(object_root, manifest)
        if str(manifest.get("generator") or "").strip() != "agent":
            raise ObjectTransactionError(
                f"DATA.POOL.GENERATOR_PROVENANCE_INVALID: {normalized_ref}"
            )
        variant_purpose = str(manifest.get("variantPurpose") or "original").strip()
        if variant_purpose not in {"original", "commercial_variant"}:
            raise ObjectTransactionError(
                f"DATA.POOL.VARIANT_INVALID: {normalized_ref}"
            )
        if variant_purpose == "commercial_variant" and usage_scope != "commercial":
            raise ObjectTransactionError(
                f"DATA.POOL.VARIANT_SCOPE_INVALID: {normalized_ref}"
            )
    else:
        carrier = "homepage"
        author_id = None
        variant_purpose = "not_applicable"

    payload_digest = str(record.get("payloadDigest") or "").strip()
    canonical_object_digest = str(record.get("canonicalObjectDigest") or "").strip()
    evidence_ref = str(record.get("evidenceRef") or "").strip()
    evidence_digest = str(record.get("evidenceDigest") or "").strip()
    if (
        not _DIGEST.fullmatch(payload_digest)
        or not _DIGEST.fullmatch(canonical_object_digest)
        or canonical_object_digest != payload_digest
        or not evidence_ref
        or not _DIGEST.fullmatch(evidence_digest)
    ):
        raise ObjectTransactionError(
            f"DATA.POOL.RECORD_DIGEST_INVALID: {kind}/{normalized_ref}"
        )

    binding_ref, bindings, binding_digest = _content_library_bindings(
        object_root,
        manifest,
    )
    selection_identity: dict[str, object] = {
        "schema": "quwoquan_data.content_pool_selection_identity",
        "objectType": normalized_type,
        "objectId": object_id,
        "objectRef": normalized_ref,
        "carrier": carrier,
        "contentVersion": content_version,
        "authorId": author_id,
        "status": status,
        "processResult": str(record.get("processResult") or ""),
        "qualityResult": str(record.get("qualityResult") or ""),
        "eligibilityResult": str(record.get("eligibilityResult") or ""),
        "usageScope": usage_scope,
        "variantPurpose": variant_purpose,
        "contentLibraryBindingDigest": binding_digest,
    }
    result = ContentPoolHandoffQuery(
        object_type=normalized_type,
        object_id=object_id,
        object_ref=normalized_ref,
        carrier=carrier,
        content_version=content_version,
        record_sequence=record_sequence,
        author_id=author_id,
        status=status,
        process_result=str(record.get("processResult") or ""),
        quality_result=str(record.get("qualityResult") or ""),
        eligibility_result=str(record.get("eligibilityResult") or ""),
        usage_scope=usage_scope,
        variant_purpose=variant_purpose,
        evidence_ref=evidence_ref,
        evidence_digest=evidence_digest,
        payload_digest=payload_digest,
        canonical_object_digest=canonical_object_digest,
        selection_identity_digest=_canonical_digest(selection_identity),
        canonical_object_ref=f"{kind}/{normalized_ref}",
        manifest_ref=f"{kind}/{normalized_ref}/manifest.json",
        pool_record_ref=(
            f"{kind}/{normalized_ref}/_pool/versions/{record_sequence}.json"
        ),
        content_library_binding_ref=(
            f"{kind}/{normalized_ref}/{binding_ref}" if binding_ref else None
        ),
        content_library_binding_digest=binding_digest,
        content_library_bindings=bindings,
    )
    result.as_document()
    return result


__all__ = [
    "ContentLibraryBinding",
    "ContentPoolHandoffQuery",
    "project_content_pool_handoff",
]
