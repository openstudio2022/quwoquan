"""Validate object-local closures for pool-wide immutable releases."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from content.release.canonical.aggregate_release_closure import (
    object_root,
    reference_closure,
)
from content.release.canonical.content_pool_record import (
    is_pool_record_admitted,
)
from content.release.canonical.creator_avatar_quality import (
    creator_avatar_quality_issues,
)
from content.release.canonical.effective_admission import (
    effective_admission_record as _effective_record,
)
from content.release.canonical.effective_admission import (
    effective_source_attribution_ready,
    resolve_effective_admission,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from content.release.canonical.release_admission import (
    build_release_asset_admission,
)
from core.media_asset_url import build_release_media_manifest


def selected_pool_entity_refs(
    publish_root: Path,
    *,
    post_refs: set[str],
) -> set[str]:
    entity_refs: set[str] = set()
    for post_ref in sorted(post_refs):
        manifest = _read_json(
            object_root(publish_root, "posts", post_ref) / "manifest.json"
        )
        raw_refs = manifest.get("entityRefs")
        if not isinstance(raw_refs, list) or not raw_refs:
            raise ObjectTransactionError(
                f"DATA.POOL.REFERENCE_MISSING: posts/{post_ref} has no entityRefs"
            )
        for raw_ref in raw_refs:
            value = str(raw_ref or "").strip()
            if not value.startswith("/entity/") or len(value) <= len("/entity/"):
                raise ObjectTransactionError(
                    f"DATA.POOL.REFERENCE_INVALID: posts/{post_ref} entityRef={value!r}"
                )
            ref = value.removeprefix("/entity/")
            if not (
                object_root(publish_root, "entities", ref) / "manifest.json"
            ).is_file():
                raise ObjectTransactionError(
                    f"DATA.POOL.REFERENCE_MISSING: posts/{post_ref} entityRef={value}"
                )
            entity_refs.add(ref)
    return entity_refs


def pool_execution_ids(
    publish_root: Path,
    *,
    entity_refs: set[str],
    post_refs: set[str],
) -> list[str]:
    identities: set[str] = set()
    for kind, refs in (("entities", entity_refs), ("posts", post_refs)):
        for ref in sorted(refs):
            root = object_root(publish_root, kind, ref)
            manifest = _read_json(root / "manifest.json")
            record = _effective_record(
                root,
                manifest,
                object_type=("homepage" if kind == "entities" else "content"),
            )
            source_identity = (
                record.get("sourceIdentity") if isinstance(record, Mapping) else None
            )
            identity = str(
                source_identity.get("executionId")
                if isinstance(source_identity, Mapping)
                else ""
            ).strip()
            if not identity:
                raise ObjectTransactionError(
                    f"DATA.POOL.SOURCE_TASK_MISSING: {kind}/{ref}"
                )
            identities.add(identity)
    return sorted(identities)


def _validate_entity_pool_identity(
    publish_root: Path,
    *,
    entity_refs: set[str],
    release_class: str,
) -> None:
    for entity_ref in sorted(entity_refs):
        root = object_root(publish_root, "entities", entity_ref)
        manifest = _read_json(root / "manifest.json")
        admission = resolve_effective_admission(
            root,
            object_type="homepage",
            document=manifest,
        )
        record = admission.record
        if not is_pool_record_admitted(record):
            raise ObjectTransactionError(
                f"DATA.POOL.OBJECT_NOT_ADMITTED: entities/{entity_ref}"
            )
        if (
            release_class == "commercial"
            and record.get("usageScope") != "commercial"
        ):
            raise ObjectTransactionError(
                f"DATA.POOL.COMMERCIAL_RIGHTS_REQUIRED: entities/{entity_ref}"
            )
        entity_id = str(record.get("objectId") or "").strip()
        version = record.get("contentVersion")
        if (
            not entity_id
            or isinstance(version, bool)
            or not isinstance(version, int)
            or version < 1
        ):
            raise ObjectTransactionError(
                f"DATA.POOL.IDENTITY_INVALID: entities/{entity_ref}"
            )
        if not effective_source_attribution_ready(admission):
            raise ObjectTransactionError(
                f"DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE: entities/{entity_ref}"
            )


def release_authors(
    publish_root: Path,
    *,
    creator_refs: list[str],
    strict_admission: bool,
) -> list[dict[str, object]]:
    authors: list[dict[str, object]] = []
    for creator_ref in sorted(creator_refs):
        profile = _read_json(
            object_root(publish_root, "creators", creator_ref) / "profile.json"
        )
        creator_root = object_root(publish_root, "creators", creator_ref)
        record = _effective_record(
            creator_root,
            profile,
            object_type="author",
        )
        version = (
            record.get("contentVersion")
            if record is not None
            else profile.get("version")
        )
        if strict_admission and not is_pool_record_admitted(record):
            raise ObjectTransactionError(
                f"DATA.POOL.AUTHOR_NOT_ADMITTED: creators/{creator_ref}"
            )
        authors.append(
            {
                "authorId": creator_ref,
                "version": version if isinstance(version, int) and version > 0 else 1,
                "creatorRef": creator_ref,
            }
        )
    return authors


def candidate_closure(
    publish_root: Path,
    *,
    post_ref: str,
    release_class: str,
) -> tuple[set[str], list[str], list[str], list[dict[str, object]]]:
    """Validate one selectable Post and only its runtime dependencies."""

    post_refs = {post_ref}
    entity_refs = selected_pool_entity_refs(
        publish_root,
        post_refs=post_refs,
    )
    _validate_entity_pool_identity(
        publish_root,
        entity_refs=entity_refs,
        release_class=release_class,
    )
    creator_refs, tag_refs = reference_closure(
        publish_root,
        entity_refs=entity_refs,
        post_refs=post_refs,
    )
    release_authors(
        publish_root,
        creator_refs=creator_refs,
        strict_admission=True,
    )
    creator_issues = [
        issue
        for issue in creator_avatar_quality_issues(
            publish_root,
            creator_refs=creator_refs,
        )
        # Missing avatars use the platform default at runtime. A declared but
        # corrupt avatar remains an object-local delivery error.
        if issue.get("code") != "creator_avatar_missing"
    ]
    if creator_issues:
        raise ObjectTransactionError(
            "DATA.POOL.AUTHOR_CLOSURE_INVALID: "
            + "; ".join(f"{item['code']}:{item['ref']}" for item in creator_issues[:5])
        )
    media_manifest = build_release_media_manifest(
        release_id="pool-candidate-preflight",
        post_refs=[post_ref],
        entity_refs=sorted(entity_refs),
        creator_refs=creator_refs,
        publish_root=publish_root,
        release_class=release_class,
    )
    if media_manifest["issues"]:
        raise ObjectTransactionError(
            "DATA.POOL.MEDIA_CLOSURE_INVALID: "
            + "; ".join(str(issue) for issue in media_manifest["issues"][:5])
        )
    try:
        build_release_asset_admission(
            release_id="pool-candidate-preflight",
            objects_root=publish_root,
            desired={
                "creators": creator_refs,
                "entities": sorted(entity_refs),
                "posts": [post_ref],
                "tags": tag_refs,
            },
            release_class=release_class,
        )
    except ObjectTransactionError as exc:
        if release_class == "commercial" and str(exc).startswith(
            "commercial release contains non-commercial assets"
        ):
            raise ObjectTransactionError(
                f"DATA.POOL.COMMERCIAL_RIGHTS_REQUIRED: posts/{post_ref}"
            ) from exc
        raise
    return entity_refs, creator_refs, tag_refs, list(media_manifest["assets"])


def entity_candidate_closure(
    publish_root: Path,
    *,
    entity_ref: str,
    release_class: str,
) -> tuple[list[str], list[str]]:
    entity_refs = {entity_ref}
    _validate_entity_pool_identity(
        publish_root,
        entity_refs=entity_refs,
        release_class=release_class,
    )
    creator_refs, tag_refs = reference_closure(
        publish_root,
        entity_refs=entity_refs,
        post_refs=set(),
    )
    release_authors(
        publish_root,
        creator_refs=creator_refs,
        strict_admission=True,
    )
    creator_issues = [
        issue
        for issue in creator_avatar_quality_issues(
            publish_root,
            creator_refs=creator_refs,
        )
        if issue.get("code") != "creator_avatar_missing"
    ]
    if creator_issues:
        raise ObjectTransactionError(
            "DATA.POOL.AUTHOR_CLOSURE_INVALID: "
            + "; ".join(f"{item['code']}:{item['ref']}" for item in creator_issues[:5])
        )
    media_manifest = build_release_media_manifest(
        release_id="pool-homepage-preflight",
        post_refs=[],
        entity_refs=[entity_ref],
        creator_refs=creator_refs,
        publish_root=publish_root,
        release_class=release_class,
    )
    if media_manifest["issues"]:
        raise ObjectTransactionError(
            "DATA.POOL.MEDIA_CLOSURE_INVALID: "
            + "; ".join(str(issue) for issue in media_manifest["issues"][:5])
        )
    try:
        build_release_asset_admission(
            release_id="pool-homepage-preflight",
            objects_root=publish_root,
            desired={
                "creators": creator_refs,
                "entities": [entity_ref],
                "posts": [],
                "tags": tag_refs,
            },
            release_class=release_class,
        )
    except ObjectTransactionError as exc:
        if release_class == "commercial" and str(exc).startswith(
            "commercial release contains non-commercial assets"
        ):
            raise ObjectTransactionError(
                f"DATA.POOL.COMMERCIAL_RIGHTS_REQUIRED: entities/{entity_ref}"
            ) from exc
        raise
    return creator_refs, tag_refs


def media_identity(asset: Mapping[str, object]) -> tuple[object, ...]:
    return tuple(
        asset.get(field)
        for field in (
            "kind",
            "version",
            "contentType",
            "publicSliceKey",
            "privateObjectKey",
            "sha256",
            "bytes",
        )
    )


__all__ = [
    "candidate_closure",
    "entity_candidate_closure",
    "media_identity",
    "pool_execution_ids",
    "release_authors",
    "selected_pool_entity_refs",
]
