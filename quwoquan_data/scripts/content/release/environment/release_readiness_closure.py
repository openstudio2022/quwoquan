"""Exact immutable-object and environment-readback closure for readiness."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.environment.release_readiness_support import (
    ReleaseReadinessClosureError,
    _assert_attestation_projection,
    _assert_import_counts,
    _assert_media_rights_closure,
    _assert_probe_matches_asset,
    _media_rows,
    _normalized_ref,
    _object,
    _text,
    _url_slice,
)
from core.release_layout import payload_file


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

    # DEC-031：research 私有交付的回读证据以相对 CAS key 闭合、不做匿名取回
    # 探测；commercial 保持匿名 CDN URL 与逐资产取回探测闭合。
    research_release = header.get("releaseClass") == "research"
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
            payload_file(release_root, f"objects/tags/{normalized}/_definition.json"),
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
            raise ReleaseReadinessClosureError(
                "release media ownerRefs must be an array"
            )
        for owner_ref in owner_refs:
            owner_assets.setdefault(str(owner_ref), []).append(row)

    creator_rows = [
        row for row in post_report.get("creators") or [] if isinstance(row, Mapping)
    ]
    creator_evidence = {
        _normalized_ref(row.get("creatorRef"), kind="creators"): row
        for row in creator_rows
    }
    expected_creator_refs = {
        _normalized_ref(ref, kind="creators") for ref in desired["creators"]
    }
    if set(creator_evidence) != expected_creator_refs or len(creator_rows) != len(
        creator_evidence
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
            payload_file(release_root, f"objects/creators/{normalized}/profile.json"),
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
        # research：avatar 不做匿名取回探测（avatarProbeCount=0）；
        # commercial：逐资产全量取回探测（avatarProbeCount=1）。
        expected_probe_count = 0 if research_release else 1
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
            or evidence.get("avatarProbeCount") != expected_probe_count
            or evidence.get("usesPlatformDefaultAvatar") is not False
        ):
            raise ReleaseReadinessClosureError(
                f"creator/avatar readback drifts from release object: {normalized}"
            )
        if research_release:
            if (
                evidence.get("avatarProbe") is not None
                or evidence.get("avatarUrl") != media.get("privateObjectKey")
            ):
                raise ReleaseReadinessClosureError(
                    f"creator avatar private delivery drifts: {normalized}"
                )
        else:
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
            payload_file(release_root, f"objects/entities/{normalized}/_entity.json"),
            label=f"release entity object {normalized}",
        )
        creator_ref = _normalized_ref(entity.get("creatorProfileId"), kind="creators")
        entity_tags = {
            _normalized_ref(tag, kind="tags") for tag in entity.get("tagRefs") or []
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
        # DEC-031：research 的 homepage 封面回读是相对 CAS key，直接与
        # privateObjectKey 闭合；commercial 是匿名 CDN URL，取 path 段与
        # publicSliceKey 闭合。
        if research_release:
            cover_slice = (
                _text(
                    row.get("coverUrl"),
                    label=f"homepage cover ref {normalized}",
                ).lstrip("/")
                if row is not None
                else ""
            )
            delivery_key_field = "privateObjectKey"
        else:
            cover_slice = (
                _url_slice(
                    row.get("coverUrl"), label=f"homepage cover URL {normalized}"
                )
                if row is not None
                else ""
            )
            delivery_key_field = "publicSliceKey"
        candidates = [
            asset
            for asset in owner_assets.get(f"entities/{normalized}", [])
            if asset.get("kind") == "image"
            and asset.get(delivery_key_field) == cover_slice
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
    # post 域对象闭包：research readback（GetResearchReleaseReadback）按
    # posts 集合聚合 entityRefs（runtime 规范形态）与 post 拥有的媒体资产，
    # readiness 用同口径的 release 权威值与之精确闭合。
    post_entity_refs: set[str] = set()
    post_media_asset_ids: set[str] = set()
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
            _normalized_ref(tag, kind="tags") for tag in manifest.get("tagRefs") or []
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
            or manifest.get("authorId") != creator_author_ids.get(manifest_creator_ref)
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
            if (
                not isinstance(attribution, Mapping)
                or not str(attribution.get("attributionText") or "").strip()
            ):
                raise ReleaseReadinessClosureError(
                    f"release video attribution is missing: {post_ref}"
                )
        for entity_runtime_ref in manifest.get("normalizedEntityRefs") or []:
            normalized_entity_ref = str(entity_runtime_ref or "").strip()
            if normalized_entity_ref:
                post_entity_refs.add(normalized_entity_ref)
        owned = owner_assets.get(f"posts/{post_ref}", [])
        for asset in owned:
            post_media_asset_ids.add(
                _text(asset.get("assetId"), label=f"owned media assetId {post_ref}")
            )
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
            if research_release:
                probe = probes_by_id[asset_id]
                if (
                    probe.get("deliveryRef") != asset.get("privateObjectKey")
                    or probe.get("anonymousStatus") not in {401, 403}
                    or probe.get("expectedSha256") != asset.get("sha256")
                    or probe.get("expectedBytes") != asset.get("bytes")
                ):
                    raise ReleaseReadinessClosureError(
                        f"research media probe drifts from release authority: {asset_id}"
                    )
            else:
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
        "postEntityRefs": post_entity_refs,
        "postMediaAssetIds": post_media_asset_ids,
    }


__all__ = [
    "ReleaseReadinessClosureError",
    "validate_readiness_closure",
]
