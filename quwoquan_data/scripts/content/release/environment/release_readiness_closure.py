"""Exact immutable-object and environment-readback closure for readiness."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from core.io import read_json
from core.release_layout import object_closure_digest, payload_file


class ReleaseReadinessClosureError(ValueError):
    """The release graph and its environment readback do not close exactly."""


def _object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise ReleaseReadinessClosureError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, Mapping):
        raise ReleaseReadinessClosureError(f"{label} must be an object: {path}")
    return dict(value)


def _text(value: object, *, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ReleaseReadinessClosureError(f"{label} must be non-empty")
    return result


def _normalized_ref(value: object, *, kind: str) -> str:
    result = _text(value, label=f"{kind} ref").strip("/")
    singular = {"creators": "creator", "entities": "entity", "posts": "post", "tags": "tag"}.get(kind)
    if singular is None:
        raise ReleaseReadinessClosureError(f"unsupported release object kind: {kind}")
    prefixes = (f"{kind}/", f"{singular}/")
    for prefix in prefixes:
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break
    if not result or ".." in Path(result).parts:
        raise ReleaseReadinessClosureError(f"unsafe {kind} ref: {value}")
    return result


def _url_slice(value: object, *, label: str, allow_query: bool = False) -> str:
    parsed = urlsplit(_text(value, label=label))
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or (parsed.query and not allow_query)
        or parsed.fragment
    ):
        raise ReleaseReadinessClosureError(f"{label} must be one canonical HTTPS URL")
    return parsed.path.lstrip("/")


def _media_rows(media_manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    assets = media_manifest.get("assets")
    issues = media_manifest.get("issues")
    counts = media_manifest.get("counts")
    if not isinstance(assets, list) or not isinstance(issues, list) or issues:
        raise ReleaseReadinessClosureError(
            "release media manifest must contain an issue-free asset array"
        )
    if not isinstance(counts, Mapping) or counts.get("assets") != len(assets) or counts.get(
        "issues"
    ) != len(issues):
        raise ReleaseReadinessClosureError("release media manifest counts drift")
    result: dict[str, dict[str, Any]] = {}
    for raw in assets:
        if not isinstance(raw, Mapping):
            raise ReleaseReadinessClosureError("release media asset must be an object")
        row = dict(raw)
        asset_id = _text(row.get("assetId"), label="release media assetId")
        if asset_id in result:
            raise ReleaseReadinessClosureError(
                f"release media assetId is duplicated: {asset_id}"
            )
        result[asset_id] = row
    if not result:
        raise ReleaseReadinessClosureError("release media manifest must not be empty")
    return result


def _assert_media_rights_closure(
    *,
    release_root: Path,
    media_by_id: Mapping[str, Mapping[str, Any]],
    desired: Mapping[str, list[str]],
) -> None:
    allowed_owners = {
        f"{kind}/{_normalized_ref(ref, kind=kind)}"
        for kind in ("creators", "entities", "posts")
        for ref in desired[kind]
    }
    for asset_id, asset in media_by_id.items():
        owner_refs = asset.get("ownerRefs")
        rights_refs = asset.get("rightsSnapshotRefs")
        if (
            not isinstance(owner_refs, list)
            or not owner_refs
            or len(owner_refs) != len(set(owner_refs))
            or not set(owner_refs).issubset(allowed_owners)
            or not isinstance(rights_refs, list)
            or not rights_refs
            or len(rights_refs) != len(set(rights_refs))
        ):
            raise ReleaseReadinessClosureError(
                f"release media owner/rights refs are not canonical: {asset_id}"
            )
        owners_with_rights: set[str] = set()
        for raw_ref in rights_refs:
            rights_ref = str(raw_ref or "").strip()
            candidate = Path(rights_ref)
            marker = "/rights_snapshots/"
            if (
                candidate.is_absolute()
                or candidate.as_posix() != rights_ref
                or ".." in candidate.parts
                or not rights_ref.startswith("objects/")
                or marker not in rights_ref
                or not rights_ref.endswith(".json")
            ):
                raise ReleaseReadinessClosureError(
                    f"release media rights ref is not canonical: {asset_id}"
                )
            owner = rights_ref.removeprefix("objects/").split(marker, 1)[0]
            if owner not in owner_refs:
                raise ReleaseReadinessClosureError(
                    f"release media rights owner drifts: {asset_id}"
                )
            rights = _object(
                payload_file(release_root, rights_ref),
                label=f"release media rights snapshot {asset_id}",
            )
            manifest_asset = rights.get("manifestAsset")
            if (
                rights.get("assetId") != asset_id
                or not isinstance(manifest_asset, Mapping)
                or manifest_asset.get("assetId") != asset_id
                or manifest_asset.get("sha256") != asset.get("sha256")
            ):
                raise ReleaseReadinessClosureError(
                    f"release media rights identity drifts: {asset_id}"
                )
            owners_with_rights.add(owner)
        if owners_with_rights != set(owner_refs):
            raise ReleaseReadinessClosureError(
                f"release media owner lacks rights snapshot: {asset_id}"
            )


def _assert_attestation_projection(
    *,
    release_root: Path,
    header: Mapping[str, Any],
    attestation: Mapping[str, Any],
    desired: Mapping[str, list[str]],
) -> None:
    projected_fields = (
        "releaseId",
        "sourceOwner",
        "releaseKind",
        "releaseClass",
        "productLifecycleState",
        "containsUnverifiedAssets",
        "rightsStatusCounts",
        "authorizationRequiredAssetIds",
        "researchAcceptedCount",
        "commercialAcceptedCount",
        "executionIds",
        "canonicalMerkle",
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
        "sourceDigests",
    )
    drifted = [
        field
        for field in projected_fields
        if attestation.get(field) != header.get(field)
    ]
    if drifted:
        raise ReleaseReadinessClosureError(
            "release attestation/header projection drift: " + ", ".join(drifted)
        )
    expected_counts = {
        "entityCount": len(desired["entities"]),
        "postCount": len(desired["posts"]),
        "creatorCount": len(desired["creators"]),
        "tagCount": len(desired["tags"]),
    }
    if any(attestation.get(field) != value for field, value in expected_counts.items()):
        raise ReleaseReadinessClosureError(
            "release attestation object counts drift from desiredRefs"
        )
    actual_merkle = object_closure_digest(release_root)
    if header.get("canonicalMerkle") != actual_merkle:
        raise ReleaseReadinessClosureError(
            "release canonicalMerkle drifts from immutable object closure"
        )


def _assert_import_counts(
    *,
    import_report: Mapping[str, Any],
    creator_report: Mapping[str, Any],
    desired: Mapping[str, list[str]],
) -> None:
    content_counts = import_report.get("counts")
    creator_counts = creator_report.get("counts")
    if not isinstance(content_counts, Mapping) or (
        content_counts.get("postsLoaded") != len(desired["posts"])
        or content_counts.get("entitiesLoaded") != len(desired["entities"])
    ):
        raise ReleaseReadinessClosureError(
            "content import counts drift from immutable desiredRefs"
        )
    if not isinstance(creator_counts, Mapping) or creator_counts.get(
        "creatorsLoaded"
    ) != len(desired["creators"]):
        raise ReleaseReadinessClosureError(
            "creator import counts drift from immutable desiredRefs"
        )


def _assert_probe_matches_asset(
    *,
    probe: Mapping[str, Any],
    asset: Mapping[str, Any],
    require_full_hash: bool,
) -> None:
    asset_id = _text(asset.get("assetId"), label="release media assetId")
    expected_kind = "video" if asset.get("kind") == "video" else "image"
    expected_fields_present = (
        "expectedBytes" in probe or "expectedSha256" in probe
    )
    if (
        (
            probe.get("kind") != expected_kind
            and not (asset.get("kind") == "avatar" and "kind" not in probe)
        )
        or (
            expected_fields_present
            and (
                probe.get("expectedBytes") != asset.get("bytes")
                or probe.get("expectedSha256") != asset.get("sha256")
            )
        )
        or probe.get("mimeType") != asset.get("contentType")
        or _url_slice(
            probe.get("publicUrl"),
            label=f"media probe URL {asset_id}",
            allow_query=asset.get("kind") == "avatar",
        )
        != asset.get("publicSliceKey")
    ):
        raise ReleaseReadinessClosureError(
            f"media probe drifts from release authority: {asset_id}"
        )
    if require_full_hash:
        if (
            probe.get("status") != 200
            or probe.get("hashVerified") is not True
            or probe.get("bytes") != asset.get("bytes")
            or probe.get("sha256") != asset.get("sha256")
        ):
            raise ReleaseReadinessClosureError(
                f"image probe lacks full release identity: {asset_id}"
            )
    elif (
        not expected_fields_present
        or probe.get("status") != 206
        or probe.get("hashVerified") is not False
        or not str(probe.get("mimeType") or "").startswith("video/")
        or int(probe.get("bytes") or 0) <= 0
        or int(probe.get("bytes") or 0) > int(asset.get("bytes") or 0)
    ):
        raise ReleaseReadinessClosureError(
            f"video probe lacks playable byte-range evidence: {asset_id}"
        )


def validate_readiness_closure(
    *,
    release_root: Path,
    header: Mapping[str, Any],
    desired: Mapping[str, list[str]],
    attestation: Mapping[str, Any],
    asset_admission: Mapping[str, Any],
    media_manifest: Mapping[str, Any],
    import_report: Mapping[str, Any],
    creator_report: Mapping[str, Any],
    homepage_report: Mapping[str, Any],
    post_report: Mapping[str, Any],
) -> dict[str, set[str]]:
    """Validate and return exact IDs proven by the immutable object graph."""

    _assert_attestation_projection(
        release_root=release_root,
        header=header,
        attestation=attestation,
        desired=desired,
    )
    _assert_import_counts(
        import_report=import_report,
        creator_report=creator_report,
        desired=desired,
    )
    coverage = asset_admission.get("articleMediaCoverage")
    # Coverage is a truthful operating statistic. A text-only Article remains
    # a valid Research object; only an Article declared illustrated must close
    # its own cover/body media references.
    if not isinstance(coverage, Mapping):
        raise ReleaseReadinessClosureError(
            "release articleMediaCoverage statistics are missing"
        )
    desired_tag_refs = {
        _normalized_ref(tag_ref, kind="tags") for tag_ref in desired["tags"]
    }
    for normalized in sorted(desired_tag_refs):
        tag = _object(
            payload_file(
                release_root, f"objects/tags/{normalized}/_definition.json"
            ),
            label=f"release tag definition {normalized}",
        )
        _text(tag.get("label"), label=f"release tag label {normalized}")

    media_by_id = _media_rows(media_manifest)
    _assert_media_rights_closure(
        release_root=release_root,
        media_by_id=media_by_id,
        desired=desired,
    )
    owner_assets: dict[str, list[dict[str, Any]]] = {}
    for row in media_by_id.values():
        owner_refs = row.get("ownerRefs")
        if not isinstance(owner_refs, list):
            raise ReleaseReadinessClosureError("release media ownerRefs must be an array")
        for owner_ref in owner_refs:
            owner_assets.setdefault(str(owner_ref), []).append(row)

    creator_rows = [
        row
        for row in post_report.get("creators") or []
        if isinstance(row, Mapping)
    ]
    creator_evidence = {
        _normalized_ref(row.get("creatorRef"), kind="creators"): row
        for row in creator_rows
    }
    expected_creator_refs = {
        _normalized_ref(ref, kind="creators") for ref in desired["creators"]
    }
    if (
        set(creator_evidence) != expected_creator_refs
        or len(creator_rows) != len(creator_evidence)
    ):
        raise ReleaseReadinessClosureError(
            "creator API evidence does not exactly close desired creators"
        )
    author_ids: list[str] = []
    creator_author_ids: dict[str, str] = {}
    avatar_ids: set[str] = set()
    for creator_ref in desired["creators"]:
        normalized = _normalized_ref(creator_ref, kind="creators")
        profile = _object(
            payload_file(
                release_root, f"objects/creators/{normalized}/profile.json"
            ),
            label=f"release creator profile {normalized}",
        )
        author_id = _text(
            profile.get("authorId"), label=f"creator authorId {normalized}"
        )
        persona_id = _text(
            profile.get("personaId"), label=f"creator personaId {normalized}"
        )
        avatar = profile.get("avatarAsset")
        evidence = creator_evidence.get(normalized)
        if avatar is None:
            if (
                evidence is None
                or evidence.get("authorId") != author_id
                or evidence.get("personaId") != persona_id
                or evidence.get("avatarAssetId") is not None
                or evidence.get("avatarUrl") != ""
                or evidence.get("avatarMediaReady") is not False
                or evidence.get("avatarProbeCount") != 0
                or evidence.get("avatarProbe") is not None
                or evidence.get("usesPlatformDefaultAvatar") is not True
            ):
                raise ReleaseReadinessClosureError(
                    f"creator default-avatar readback drifts from release object: {normalized}"
                )
            author_ids.append(author_id)
            creator_author_ids[normalized] = author_id
            continue
        if not isinstance(avatar, Mapping):
            raise ReleaseReadinessClosureError(
                f"release creator avatar binding is invalid: {normalized}"
            )
        avatar_id = _text(
            avatar.get("assetId"), label=f"creator avatarAssetId {normalized}"
        )
        media = media_by_id.get(avatar_id)
        if (
            media is None
            or evidence is None
            or media.get("kind") != "avatar"
            or f"creators/{normalized}" not in (media.get("ownerRefs") or [])
            or avatar.get("sha256") != media.get("sha256")
            or evidence.get("authorId") != author_id
            or evidence.get("personaId") != persona_id
            or evidence.get("avatarAssetId") != avatar_id
            or evidence.get("avatarMediaReady") is not True
            or evidence.get("avatarProbeCount") != 1
            or evidence.get("usesPlatformDefaultAvatar") is not False
        ):
            raise ReleaseReadinessClosureError(
                f"creator/avatar readback drifts from release object: {normalized}"
            )
        avatar_probe = evidence.get("avatarProbe")
        if not isinstance(avatar_probe, Mapping):
            raise ReleaseReadinessClosureError(
                f"creator avatar probe is missing: {normalized}"
            )
        _assert_probe_matches_asset(
            probe=avatar_probe,
            asset=media,
            require_full_hash=True,
        )
        author_ids.append(author_id)
        creator_author_ids[normalized] = author_id
        avatar_ids.add(avatar_id)
    if len(author_ids) != len(set(author_ids)):
        raise ReleaseReadinessClosureError(
            "release creators must bind unique authorIds"
        )
    if sorted(creator_report.get("authorIds") or []) != sorted(author_ids):
        raise ReleaseReadinessClosureError(
            "creator importer authorIds drift from release creator profiles"
        )

    homepage_rows = {
        _normalized_ref(row.get("entityRef"), kind="entities"): row
        for row in homepage_report.get("entities") or []
        if isinstance(row, Mapping)
    }
    for entity_ref in desired["entities"]:
        normalized = _normalized_ref(entity_ref, kind="entities")
        entity = _object(
            payload_file(
                release_root, f"objects/entities/{normalized}/_entity.json"
            ),
            label=f"release entity object {normalized}",
        )
        creator_ref = _normalized_ref(
            entity.get("creatorProfileId"), kind="creators"
        )
        entity_tags = {
            _normalized_ref(tag, kind="tags")
            for tag in entity.get("tagRefs") or []
        }
        if (
            creator_ref not in expected_creator_refs
            or entity.get("authorId") != creator_author_ids.get(creator_ref)
            or not entity_tags
            or not entity_tags.issubset(desired_tag_refs)
        ):
            raise ReleaseReadinessClosureError(
                f"homepage creator/tag closure drifts: {normalized}"
            )
        row = homepage_rows.get(normalized)
        cover_slice = (
            _url_slice(row.get("coverUrl"), label=f"homepage cover URL {normalized}")
            if row is not None
            else ""
        )
        candidates = [
            asset
            for asset in owner_assets.get(f"entities/{normalized}", [])
            if asset.get("kind") == "image"
            and asset.get("publicSliceKey") == cover_slice
        ]
        if len(candidates) != 1:
            raise ReleaseReadinessClosureError(
                f"homepage cover does not bind one release media asset: {normalized}"
            )

    binding_by_id = {
        _text(row.get("postId"), label="imported postId"): row
        for row in import_report.get("postBindings") or []
        if isinstance(row, Mapping)
    }
    post_rows = {
        _text(row.get("postId"), label="verified postId"): row
        for row in post_report.get("posts") or []
        if isinstance(row, Mapping)
    }
    image_asset_ids: set[str] = set()
    illustrated_article_ids: set[str] = set()
    verified_image_work_ids: set[str] = set()
    playable_video_ids: set[str] = set()
    for post_id, binding in binding_by_id.items():
        post_ref = _normalized_ref(binding.get("postRef"), kind="posts")
        manifest = _object(
            payload_file(release_root, f"objects/posts/{post_ref}/manifest.json"),
            label=f"release post manifest {post_ref}",
        )
        content_type = _text(
            binding.get("contentType"), label=f"post contentType {post_ref}"
        )
        manifest_tags = {
            _normalized_ref(tag, kind="tags")
            for tag in manifest.get("tagRefs") or []
        }
        manifest_creator_ref = _normalized_ref(
            manifest.get("creatorProfileId"), kind="creators"
        )
        row = post_rows.get(post_id)
        if (
            row is None
            or manifest.get("contentIdentity") != "work"
            or manifest.get("contentType") != content_type
            or row.get("contentType") != content_type
            or manifest_creator_ref not in creator_author_ids
            or manifest.get("authorId")
            != creator_author_ids.get(manifest_creator_ref)
            or binding.get("authorId") != manifest.get("authorId")
            or row.get("authorId") != manifest.get("authorId")
            or not manifest_tags
            or not manifest_tags.issubset(desired_tag_refs)
        ):
            raise ReleaseReadinessClosureError(
                f"post readback drifts from release work object: {post_ref}"
            )
        if content_type == "video":
            attribution = manifest.get("sourceAttribution")
            if not isinstance(attribution, Mapping) or not str(
                attribution.get("attributionText") or ""
            ).strip():
                raise ReleaseReadinessClosureError(
                    f"release video attribution is missing: {post_ref}"
                )
        owned = owner_assets.get(f"posts/{post_ref}", [])
        probes = row.get("mediaProbes")
        if not isinstance(probes, list):
            raise ReleaseReadinessClosureError(
                f"post mediaProbes must be an array: {post_ref}"
            )
        probes_by_id = {
            _text(probe.get("assetId"), label=f"media probe assetId {post_ref}"): probe
            for probe in probes
            if isinstance(probe, Mapping)
        }
        if set(probes_by_id) != {
            _text(asset.get("assetId"), label=f"owned media assetId {post_ref}")
            for asset in owned
        }:
            raise ReleaseReadinessClosureError(
                f"post media probes do not exactly close release media: {post_ref}"
            )
        image_count = 0
        video_count = 0
        for asset in owned:
            asset_id = _text(
                asset.get("assetId"), label=f"owned media assetId {post_ref}"
            )
            require_full_hash = asset.get("kind") != "video"
            _assert_probe_matches_asset(
                probe=probes_by_id[asset_id],
                asset=asset,
                require_full_hash=require_full_hash,
            )
            if require_full_hash:
                image_count += 1
                image_asset_ids.add(asset_id)
            else:
                video_count += 1
        if content_type == "article":
            if image_count >= 2:
                illustrated_article_ids.add(post_id)
            elif manifest.get("publishMediaMode") != "text_only" or owned:
                raise ReleaseReadinessClosureError(
                    f"article lacks cover/body release media closure: {post_ref}"
                )
        elif content_type == "image":
            if image_count < 1 or video_count:
                raise ReleaseReadinessClosureError(
                    f"image work lacks exact image media closure: {post_ref}"
                )
            verified_image_work_ids.add(post_id)
        elif content_type == "video":
            if image_count < 1 or video_count < 1:
                raise ReleaseReadinessClosureError(
                    f"video work lacks poster/playable media closure: {post_ref}"
                )
            playable_video_ids.add(post_id)

    return {
        "avatarAssetIds": avatar_ids,
        "imageAssetIds": image_asset_ids,
        "illustratedArticleIds": illustrated_article_ids,
        "verifiedImageWorkIds": verified_image_work_ids,
        "playableVideoIds": playable_video_ids,
        "mediaAssetIds": set(media_by_id),
    }

__all__ = [
    "ReleaseReadinessClosureError",
    "validate_readiness_closure",
]
