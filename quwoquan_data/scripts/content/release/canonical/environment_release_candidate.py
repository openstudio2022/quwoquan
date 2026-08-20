"""Canonical pool candidate discovery and delivery admission."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from content.release.canonical.content_pool_record import (
    is_pool_record_admitted,
)
from content.release.canonical.effective_admission import (
    effective_admission_record as _effective_record,
)
from content.release.canonical.effective_admission import (
    effective_source_attribution_ready,
    resolve_effective_admission,
)
from content.release.canonical.environment_release_support import (
    pool_error_code,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)

_CONTENT_TYPES = ("article", "image", "video")


@dataclass(frozen=True, slots=True)
class PoolCandidate:
    post_ref: str
    content_id: str
    version: int
    content_type: str
    author_id: str
    variant_purpose: str
    usage_scope: str
    execution_id: str = ""
    source_identity_digest: str = ""


@dataclass(frozen=True, slots=True)
class EnvironmentReleaseSelection:
    environment: str | None
    release_mode: str
    post_refs: tuple[str, ...]
    candidates: tuple[PoolCandidate, ...]
    pool_digest: str
    eligible_count: int
    counts: dict[str, int]
    excluded: tuple[PoolExclusion, ...]
    selection_scope: str
    milestone: str | None = None
    milestone_targets: Mapping[str, int] | None = None


@dataclass(frozen=True, slots=True)
class PoolExclusion:
    post_ref: str
    gate: str
    code: str


def _candidate(
    publish_root: Path,
    post_ref: str,
    *,
    strict_admission: bool,
) -> PoolCandidate | None:
    manifest_path = publish_root / "posts" / post_ref / "manifest.json"
    try:
        manifest = _read_json(manifest_path)
    except (OSError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            f"DATA.POOL.MANIFEST_INVALID: {post_ref}: {exc}"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise ObjectTransactionError(f"DATA.POOL.MANIFEST_INVALID: {post_ref}")

    content_type = str(manifest.get("contentType") or "").strip()
    author_id = str(manifest.get("authorId") or "").strip()
    creator_refs_path = manifest_path.parent / "creator.refs.json"
    if not author_id and creator_refs_path.is_file():
        raw_creator_refs = _read_json(creator_refs_path).get("creatorRefs")
        if isinstance(raw_creator_refs, list) and raw_creator_refs:
            author_id = str(raw_creator_refs[0] or "").strip()
    if content_type not in _CONTENT_TYPES or not author_id:
        raise ObjectTransactionError(
            f"DATA.POOL.IDENTITY_INVALID: {post_ref} lacks contentType/authorId"
        )

    pool_record = _effective_record(
        manifest_path.parent, manifest, object_type="content"
    )
    if pool_record is not None:
        process_result = str(pool_record.get("processResult") or "").strip()
        quality_result = str(pool_record.get("qualityResult") or "").strip()
        usage_scope = str(pool_record.get("usageScope") or "").strip()
        status = str(pool_record.get("status") or "").strip()
        version_value = pool_record.get("contentVersion")
        content_id = str(pool_record.get("objectId") or "").strip()
        if status in {"retired", "deleted"}:
            return None
        if not is_pool_record_admitted(pool_record):
            if quality_result == "failed":
                raise ObjectTransactionError(
                    f"DATA.POOL.QUALITY_FAILED: postRef={post_ref}"
                )
            raise ObjectTransactionError(
                f"DATA.POOL.ELIGIBILITY_FAILED: postRef={post_ref}"
            )
    else:
        raise ObjectTransactionError(
            f"DATA.POOL.POST_NOT_ADMITTED: postRef={post_ref} admission=<missing>"
        )
    if str(manifest.get("generator") or "").strip() != "agent":
        raise ObjectTransactionError(
            f"DATA.POOL.GENERATOR_PROVENANCE_INVALID: postRef={post_ref}"
        )
    manifest_version = manifest.get("version") or version_value
    if (
        isinstance(manifest_version, bool)
        or not isinstance(manifest_version, int)
        or manifest_version < 1
        or pool_record.get("contentVersion") != manifest_version
    ):
        raise ObjectTransactionError(
            "DATA.POOL.IDENTITY_INVALID: "
            f"postRef={post_ref} manifest/pool identity drift"
        )
    if (
        process_result != "completed"
        or quality_result != "passed"
        or status != "active"
    ):
        raise ObjectTransactionError(
            "DATA.POOL.POST_NOT_ADMITTED: "
            f"postRef={post_ref} process={process_result or '<missing>'} "
            f"quality={quality_result or '<missing>'} status={status or '<missing>'}"
        )
    if usage_scope not in {"research", "commercial"}:
        raise ObjectTransactionError(
            f"DATA.POOL.USAGE_SCOPE_INVALID: postRef={post_ref} scope={usage_scope!r}"
        )
    variant_purpose = str(manifest.get("variantPurpose") or "original").strip()
    if variant_purpose not in {"original", "commercial_variant"}:
        raise ObjectTransactionError(
            f"DATA.POOL.VARIANT_INVALID: postRef={post_ref} variant={variant_purpose!r}"
        )
    if variant_purpose == "commercial_variant" and usage_scope != "commercial":
        raise ObjectTransactionError(
            f"DATA.POOL.VARIANT_SCOPE_INVALID: postRef={post_ref}"
        )
    if (
        not isinstance(version_value, int)
        or isinstance(version_value, bool)
        or version_value < 1
    ):
        raise ObjectTransactionError(
            f"DATA.POOL.VERSION_INVALID: postRef={post_ref} version={version_value!r}"
        )
    version = version_value
    source_identity = pool_record.get("sourceIdentity")
    return PoolCandidate(
        post_ref=post_ref,
        content_id=content_id,
        version=version,
        content_type=content_type,
        author_id=author_id,
        variant_purpose=variant_purpose,
        usage_scope=usage_scope,
        execution_id=(
            str(source_identity.get("executionId") or "").strip()
            if isinstance(source_identity, Mapping)
            else ""
        ),
        source_identity_digest=(
            str(source_identity.get("identityDigest") or "").strip()
            if isinstance(source_identity, Mapping)
            else ""
        ),
    )


def _delivery_issue(
    publish_root: Path,
    *,
    post_ref: str,
    candidate: PoolCandidate,
) -> str | None:
    root = publish_root / "posts" / post_ref
    manifest = _read_json(root / "manifest.json")
    try:
        admission = resolve_effective_admission(
            root, object_type="content", document=manifest
        )
        pool_record = admission.record
    except (OSError, ObjectTransactionError, TypeError, ValueError) as exc:
        return pool_error_code(exc)
    if not is_pool_record_admitted(pool_record):
        return "DATA.POOL.OBJECT_NOT_ADMITTED"
    if not effective_source_attribution_ready(admission):
        return "DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE"
    creator_refs_path = root / "creator.refs.json"
    raw_creator_refs = (
        _read_json(creator_refs_path).get("creatorRefs")
        if creator_refs_path.is_file()
        else [candidate.author_id]
    )
    if not isinstance(raw_creator_refs, list) or not raw_creator_refs:
        return "DATA.POOL.AUTHOR_NOT_ADMITTED"
    for raw_ref in raw_creator_refs:
        creator_ref = str(raw_ref or "").strip()
        creator_root = publish_root / "creators" / creator_ref
        try:
            profile = _read_json(creator_root / "profile.json")
            author_record = _effective_record(
                creator_root, profile, object_type="author"
            )
        except (OSError, ObjectTransactionError, TypeError, ValueError):
            return "DATA.POOL.AUTHOR_NOT_ADMITTED"
        if not creator_ref or not is_pool_record_admitted(author_record):
            return "DATA.POOL.AUTHOR_NOT_ADMITTED"
    raw_entity_refs = manifest.get("entityRefs")
    if not isinstance(raw_entity_refs, list) or not raw_entity_refs:
        return "DATA.POOL.REFERENCE_MISSING"
    for raw_ref in raw_entity_refs:
        value = str(raw_ref or "").strip()
        if not value.startswith("/entity/"):
            return "DATA.POOL.REFERENCE_MISSING"
        entity_root = publish_root / "entities" / value.removeprefix("/entity/")
        try:
            entity_manifest = _read_json(entity_root / "manifest.json")
            entity_admission = resolve_effective_admission(
                entity_root, object_type="homepage", document=entity_manifest
            )
            entity_record = entity_admission.record
        except (OSError, ObjectTransactionError, TypeError, ValueError):
            return "DATA.POOL.REFERENCE_MISSING"
        if not is_pool_record_admitted(
            entity_record
        ) or not effective_source_attribution_ready(entity_admission):
            return "DATA.POOL.REFERENCE_MISSING"
    return None


__all__ = [
    "_CONTENT_TYPES",
    "EnvironmentReleaseSelection",
    "PoolCandidate",
    "PoolExclusion",
    "_candidate",
    "_delivery_issue",
]
