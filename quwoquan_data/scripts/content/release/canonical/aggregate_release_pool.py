"""Prepare pool-wide canonical release inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from content.release.canonical.aggregate_release_closure import (
    creator_tag_refs,
    object_root,
)
from content.release.canonical.aggregate_release_pool_closure import (
    candidate_closure,
    entity_candidate_closure,
    media_identity,
    pool_execution_ids,
    release_authors,
)
from content.release.canonical.content_pool_record import (
    is_pool_record_admitted,
)
from content.release.canonical.effective_admission import (
    effective_admission_record as _effective_record,
)
from content.release.canonical.environment_release_selection import (
    MILESTONE_TARGETS,
    EnvironmentReleaseSelection,
    PoolExclusion,
    select_environment_release_posts,
    select_milestone_release_posts,
)
from content.release.canonical.object_source_identity import source_identity_set
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from core.paths import CONTROL_PLANE_TAXONOMY_ROOT
from core.source_digest import FrozenSourceDigest, SourceDigest, SourceDigestError


@dataclass(frozen=True)
class PoolReleasePreparation:
    environment_selection: EnvironmentReleaseSelection
    execution_ids: list[str]
    source_digests: tuple[SourceDigest | FrozenSourceDigest, ...]
    entity_catalog_digest: str | None
    source_revision: str | None
    source_identities: tuple[dict[str, object], ...]
    source_identity_set_digest: str
    desired: dict[str, list[str]]
    excluded: tuple[dict[str, str], ...]


def _frozen_source_digest(document: object) -> SourceDigest | FrozenSourceDigest:
    try:
        return SourceDigest.from_document(document)
    except SourceDigestError:
        try:
            return FrozenSourceDigest.from_document(document)
        except SourceDigestError as exc:
            raise ObjectTransactionError(
                "DATA.POOL.SOURCE_IDENTITY_INVALID"
            ) from exc


def pool_post_refs(publish_root: Path) -> list[str]:
    posts_root = publish_root / "posts"
    if not posts_root.is_dir():
        return []
    return [
        path.parent.relative_to(posts_root).as_posix()
        for path in sorted(posts_root.rglob("manifest.json"))
    ]


def pool_entity_refs(publish_root: Path) -> list[str]:
    entities_root = publish_root / "entities"
    if not entities_root.is_dir():
        return []
    return [
        path.parent.relative_to(entities_root).as_posix()
        for path in sorted(entities_root.rglob("manifest.json"))
    ]


def _pool_source_identity_closure(
    publish_root: Path,
    *,
    entity_refs: set[str],
    post_refs: set[str],
) -> tuple[
    tuple[SourceDigest | FrozenSourceDigest, ...],
    tuple[dict[str, object], ...],
    str,
]:
    identities: list[dict[str, str]] = []
    source_digests: dict[str, SourceDigest | FrozenSourceDigest] = {}
    for kind, refs in (("entities", entity_refs), ("posts", post_refs)):
        for ref in sorted(refs):
            root = object_root(publish_root, kind, ref)
            manifest = _read_json(root / "manifest.json")
            record = _effective_record(
                root,
                manifest,
                object_type=(
                    "homepage" if kind == "entities" else "content"
                ),
            )
            identity = (
                record.get("sourceIdentity")
                if isinstance(record, dict)
                else None
            )
            if not isinstance(identity, dict):
                raise ObjectTransactionError(
                    f"DATA.POOL.SOURCE_IDENTITY_INVALID: {kind}/{ref}"
                )
            source_digest = _frozen_source_digest(manifest.get("sourceDigest"))
            source_digests[source_digest.digest] = source_digest
            identities.append(identity)
    rows, set_digest = source_identity_set(identities)
    return (
        tuple(source_digests[key] for key in sorted(source_digests)),
        tuple(rows),
        set_digest,
    )


def release_contents(
    selection: EnvironmentReleaseSelection | None,
) -> list[dict[str, object]] | None:
    if selection is None:
        return None
    return [
        {
            "contentId": candidate.content_id,
            "version": candidate.version,
            "postRef": candidate.post_ref,
            "executionId": candidate.execution_id,
            "sourceIdentityDigest": candidate.source_identity_digest,
        }
        for candidate in selection.candidates
    ]


def admitted_pool_author_refs(publish_root: Path) -> list[str]:
    """Return all active admitted Data authors, independent of Post closure."""

    creators_root = publish_root / "creators"
    if not creators_root.is_dir():
        return []
    refs: list[str] = []
    for root in sorted(creators_root.iterdir()):
        if not root.is_dir() or not (root / "profile.json").is_file():
            continue
        profile = _read_json(root / "profile.json")
        record = _effective_record(
            root,
            profile,
            object_type="author",
        )
        if is_pool_record_admitted(record):
            refs.append(root.name)
    return refs


def _exclusion(post_ref: str, exc: Exception) -> dict[str, str]:
    message = str(exc).strip() or exc.__class__.__name__
    prefix, separator, _detail = message.partition(":")
    code = prefix if separator and prefix.startswith("DATA.") else "DATA.POOL.OBJECT_INVALID"
    return {
        "postRef": post_ref,
        "category": "delivery",
        "code": code,
        "message": message,
    }


def _selection_exclusion(exclusion: PoolExclusion) -> dict[str, str]:
    return {
        "postRef": exclusion.post_ref,
        "category": exclusion.gate,
        "code": exclusion.code,
        "message": f"{exclusion.code}: postRef={exclusion.post_ref}",
    }


def prepare_pool_release(
    *,
    publish_root: Path,
    target_environment: str | None = None,
    milestone: str | None = None,
    release_class: str | None = None,
) -> PoolReleasePreparation:
    if (target_environment is None) == (milestone is None):
        raise ObjectTransactionError(
            "DATA.RELEASE.SELECTION_INVALID: choose targetEnvironment or milestone"
        )
    if milestone is not None:
        if milestone not in MILESTONE_TARGETS:
            raise ObjectTransactionError(
                f"DATA.POOL.MILESTONE_INVALID: {milestone!r}"
            )
        if release_class != "research":
            raise ObjectTransactionError(
                "DATA.RELEASE.CLASS_INVALID: milestone pool-build requires research"
            )
    elif release_class is not None:
        raise ObjectTransactionError(
            "DATA.RELEASE.CLASS_INVALID: releaseClass is only valid with milestone"
        )
    selection_environment = target_environment or "gamma"
    candidate_refs: list[str] = []
    excluded: list[dict[str, str]] = []
    content_versions: dict[tuple[str, int], str] = {}
    for post_ref in pool_post_refs(publish_root):
        try:
            individual = select_environment_release_posts(
                publish_root=publish_root,
                post_refs=[post_ref],
                environment=selection_environment,
                strict_admission=True,
            )
        except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
            excluded.append(_exclusion(post_ref, exc))
            continue
        if not individual.candidates:
            excluded.extend(
                _selection_exclusion(item) for item in individual.excluded
            )
            continue
        candidate = individual.candidates[0]
        identity = (candidate.content_id, candidate.version)
        existing_ref = content_versions.get(identity)
        if existing_ref is not None:
            excluded.append(
                {
                    "postRef": post_ref,
                    "category": "delivery",
                    "code": "DATA.POOL.VERSION_CONFLICT",
                    "message": (
                        "DATA.POOL.VERSION_CONFLICT: "
                        f"contentId={candidate.content_id} "
                        f"version={candidate.version} kept={existing_ref}"
                    ),
                }
            )
            continue
        content_versions[identity] = post_ref
        candidate_refs.append(post_ref)

    closure_cache: dict[
        str,
        tuple[set[str], list[str], list[str], list[dict[str, object]]],
    ] = {}
    while True:
        if milestone is None:
            assert target_environment is not None
            environment_selection = select_environment_release_posts(
                publish_root=publish_root,
                post_refs=candidate_refs,
                environment=target_environment,
                strict_admission=True,
            )
        else:
            environment_selection = select_milestone_release_posts(
                publish_root=publish_root,
                post_refs=candidate_refs,
                milestone=milestone,
                strict_admission=True,
            )
        rejected: set[str] = set()
        media_identities: dict[str, tuple[object, ...]] = {}
        public_slices: dict[str, str] = {}
        for post_ref in environment_selection.post_refs:
            try:
                closure = candidate_closure(
                    publish_root,
                    post_ref=post_ref,
                    release_mode=environment_selection.release_mode,
                )
                for asset in closure[3]:
                    asset_id = str(asset.get("assetId") or "").strip()
                    public_slice = str(asset.get("publicSliceKey") or "").strip()
                    identity = media_identity(asset)
                    old_identity = media_identities.get(asset_id)
                    if old_identity is not None and old_identity != identity:
                        raise ObjectTransactionError(
                            "DATA.POOL.MEDIA_IDENTITY_CONFLICT: "
                            f"postRef={post_ref} assetId={asset_id}"
                        )
                    old_asset = public_slices.get(public_slice)
                    if old_asset is not None and old_asset != asset_id:
                        raise ObjectTransactionError(
                            "DATA.POOL.MEDIA_SLICE_CONFLICT: "
                            f"postRef={post_ref} publicSliceKey={public_slice}"
                        )
                closure_cache[post_ref] = closure
                for asset in closure[3]:
                    asset_id = str(asset.get("assetId") or "").strip()
                    public_slice = str(asset.get("publicSliceKey") or "").strip()
                    media_identities[asset_id] = media_identity(asset)
                    public_slices[public_slice] = asset_id
            except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
                rejected.add(post_ref)
                excluded.append(_exclusion(post_ref, exc))
        if not rejected:
            break
        candidate_refs = [ref for ref in candidate_refs if ref not in rejected]

    post_refs = set(environment_selection.post_refs)
    entity_closure_cache: dict[str, tuple[list[str], list[str]]] = {}
    standalone_entity_refs: set[str] = set()
    for entity_ref in pool_entity_refs(publish_root):
        root = object_root(publish_root, "entities", entity_ref)
        try:
            manifest = _read_json(root / "manifest.json")
            record = _effective_record(
                root,
                manifest,
                object_type="homepage",
            )
            if not is_pool_record_admitted(record):
                continue
            if (
                environment_selection.release_mode == "commercial"
                and record.get("usageScope") != "commercial"
            ):
                continue
            closure = entity_candidate_closure(
                publish_root,
                entity_ref=entity_ref,
                release_mode=environment_selection.release_mode,
            )
            entity_closure_cache[entity_ref] = closure
            standalone_entity_refs.add(entity_ref)
        except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
            excluded.append(_exclusion(f"entities/{entity_ref}", exc))
    if not post_refs and not standalone_entity_refs:
        raise ObjectTransactionError(
            "DATA.RELEASE.NO_ELIGIBLE_CONTENT: "
            f"selection={target_environment or milestone} excluded={len(excluded)}"
        )
    post_entity_refs = {
        ref
        for post_ref in post_refs
        for ref in closure_cache[post_ref][0]
    }
    if milestone is None:
        entity_refs = post_entity_refs | standalone_entity_refs
    else:
        homepage_target = MILESTONE_TARGETS[milestone]["homepage"]
        if not post_entity_refs.issubset(standalone_entity_refs):
            missing = sorted(post_entity_refs - standalone_entity_refs)
            raise ObjectTransactionError(
                "DATA.POOL.MILESTONE_HOMEPAGE_SHORTFALL: "
                f"milestone={milestone} missing={missing[:5]}"
            )
        remaining = [
            ref
            for ref in sorted(standalone_entity_refs)
            if ref not in post_entity_refs
        ]
        if len(post_entity_refs) > homepage_target or (
            len(post_entity_refs) + len(remaining) < homepage_target
        ):
            raise ObjectTransactionError(
                "DATA.POOL.MILESTONE_HOMEPAGE_SHORTFALL: "
                f"milestone={milestone} target={homepage_target} "
                f"requiredByPosts={len(post_entity_refs)} "
                f"eligible={len(standalone_entity_refs)}"
            )
        entity_refs = post_entity_refs | set(
            remaining[: homepage_target - len(post_entity_refs)]
        )
        standalone_entity_refs = set(entity_refs)
    execution_ids = pool_execution_ids(
        publish_root,
        entity_refs=entity_refs,
        post_refs=post_refs,
    )
    source_digests, source_identities, source_identity_set_digest = (
        _pool_source_identity_closure(
            publish_root,
            entity_refs=entity_refs,
            post_refs=post_refs,
        )
    )
    # Pool-wide releases preserve the exact per-object source identity closure.
    # A scalar source identity remains reserved for execution-scoped aggregate
    # releases and must never be synthesized from a heterogeneous pool.
    source_revision = None
    entity_catalog_digest = None
    creator_refs = sorted(
        {
            ref
            for post_ref in post_refs
            for ref in closure_cache[post_ref][1]
        }
        | {
            ref
            for entity_ref in standalone_entity_refs
            for ref in entity_closure_cache[entity_ref][0]
        }
        | set(admitted_pool_author_refs(publish_root))
    )
    tag_refs = sorted(
        {
            ref
            for post_ref in post_refs
            for ref in closure_cache[post_ref][2]
        }
        | {
            ref
            for entity_ref in standalone_entity_refs
            for ref in entity_closure_cache[entity_ref][1]
        }
        | set(
            creator_tag_refs(
                publish_root,
                creator_refs=creator_refs,
                control_plane_taxonomy_root=CONTROL_PLANE_TAXONOMY_ROOT,
            )
        )
    )
    return PoolReleasePreparation(
        environment_selection=environment_selection,
        execution_ids=execution_ids,
        source_digests=source_digests,
        entity_catalog_digest=entity_catalog_digest,
        source_revision=source_revision,
        source_identities=source_identities,
        source_identity_set_digest=source_identity_set_digest,
        desired={
            "creators": creator_refs,
            "entities": sorted(entity_refs),
            "posts": sorted(post_refs),
            "tags": tag_refs,
        },
        excluded=tuple(
            sorted(excluded, key=lambda item: (item["postRef"], item["code"]))
        ),
    )


__all__ = [
    "PoolReleasePreparation",
    "admitted_pool_author_refs",
    "prepare_pool_release",
    "release_authors",
    "release_contents",
]
