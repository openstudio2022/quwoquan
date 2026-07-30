"""Resolve release-bound post, creator and media cases for public API verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from content.release.environment.importers import assert_import_report_contract
from content.release.environment.post_api_media_verification import (
    PostApiCase,
    PostApiVerificationError,
    ReleaseMediaAssetCase,
    _object,
    _required_text,
    _source_attribution,
)
from content.release.model import DeploymentEnvironment
from core.control_types import ContentType
from core.io import read_json
from core.release_layout import payload_digest, payload_file


@dataclass(frozen=True)
class CreatorProfileCase:
    creator_ref: str
    author_id: str
    persona_id: str
    avatar_asset_id: str
    avatar_url: str
    avatar_bytes: int
    avatar_sha256: str
    avatar_mime_type: str


def _normalized_post_ref(value: object) -> str:
    ref = str(value or "").strip().replace("\\", "/")
    if (
        not ref
        or ref.startswith("/")
        or ref.startswith("posts/")
        or ".." in ref.split("/")
    ):
        raise PostApiVerificationError("post reference is invalid")
    return ref


def _release_media_case(
    row: Mapping[str, Any],
    *,
    media_origin: str,
) -> ReleaseMediaAssetCase:
    asset_id = _required_text(row, "assetId", endpoint="release media asset")
    kind = _required_text(row, "kind", endpoint=f"release media asset {asset_id}")
    public_slice_key = _required_text(
        row,
        "publicSliceKey",
        endpoint=f"release media asset {asset_id}",
    ).lstrip("/")
    expected_bytes = row.get("bytes")
    expected_sha256 = _required_text(
        row,
        "sha256",
        endpoint=f"release media asset {asset_id}",
    )
    expected_mime_type = _required_text(
        row,
        "contentType",
        endpoint=f"release media asset {asset_id}",
    ).lower()
    if (
        kind not in {"avatar", "image", "video"}
        or not public_slice_key.startswith(f"media/{kind}/s/")
        or not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes <= 0
        or not expected_mime_type.startswith(
            "video/" if kind == "video" else "image/"
        )
    ):
        raise PostApiVerificationError(
            f"release media asset projection is invalid: {asset_id}"
        )
    return ReleaseMediaAssetCase(
        asset_id=asset_id,
        kind=kind,
        public_url=f"{media_origin}/{public_slice_key}",
        expected_bytes=expected_bytes,
        expected_sha256=expected_sha256,
        expected_mime_type=expected_mime_type,
    )


def _media_origin(value: str) -> str:
    parsed = urlsplit(value.strip().rstrip("/"))
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise PostApiVerificationError(
            "media delivery base URL must be one path-free HTTPS origin"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def read_post_and_creator_cases(
    *,
    environment: DeploymentEnvironment,
    release_id: str,
    release_root: Path,
    importer_report_path: Path,
    creator_importer_report_path: Path,
    media_delivery_base_url: str,
) -> tuple[list[PostApiCase], dict[str, CreatorProfileCase]]:
    """Bind importer readback to immutable creator/post/media authorities."""

    try:
        desired = read_json(payload_file(release_root, "desired_state.json"))
        report = assert_import_report_contract(
            importer_report_path,
            expected_release_id=release_id,
            expected_manifest_digest=payload_digest(release_root),
        )
        creator_report = assert_import_report_contract(
            creator_importer_report_path,
            expected_release_id=release_id,
        )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        raise PostApiVerificationError(f"post import evidence is invalid: {exc}") from exc
    if desired.get("schema") != "quwoquan_data.release_desired_state":
        raise PostApiVerificationError("release desired state schema is invalid")
    if str(desired.get("releaseId") or "") != release_id:
        raise PostApiVerificationError("release desired state releaseId mismatch")
    if report.get("status") != "active":
        raise PostApiVerificationError("post importer report is not active")
    if creator_report.get("status") != "active":
        raise PostApiVerificationError("creator importer report is not active")
    if str(report.get("environment") or "") != environment.value:
        raise PostApiVerificationError("post importer report environment mismatch")
    desired_refs = _object(desired.get("desiredRefs"), label="release desiredRefs")
    expected = {
        _normalized_post_ref(value)
        for value in desired_refs.get("posts", [])
        if str(value or "").strip()
    }
    raw_creator_refs = desired_refs.get("creators", [])
    if not isinstance(raw_creator_refs, list):
        raise PostApiVerificationError("release desiredRefs.creators must be an array")
    media_origin = _media_origin(media_delivery_base_url)
    try:
        media_manifest = _object(
            read_json(payload_file(release_root, "media_manifest.json")),
            label="release media manifest",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise PostApiVerificationError(
            f"release media manifest is unreadable: {exc}"
        ) from exc
    media_assets = {
        _required_text(row, "assetId", endpoint="release media asset"): row
        for raw in media_manifest.get("assets") or []
        if isinstance(raw, Mapping)
        for row in [_object(raw, label="release media asset")]
    }
    creators_by_author: dict[str, CreatorProfileCase] = {}
    for raw_ref in raw_creator_refs:
        creator_ref = _normalized_post_ref(raw_ref)
        try:
            profile = _object(
                read_json(
                    release_root
                    / "payload"
                    / "objects"
                    / "creators"
                    / creator_ref
                    / "profile.json"
                ),
                label=f"creator profile {creator_ref}",
            )
        except (OSError, TypeError, ValueError) as exc:
            raise PostApiVerificationError(
                f"creator profile is unreadable for {creator_ref}: {exc}"
            ) from exc
        if profile.get("schema") != "quwoquan_data.creator_profile":
            raise PostApiVerificationError(
                f"creator profile schema is invalid: {creator_ref}"
            )
        author_id = _required_text(
            profile,
            "authorId",
            endpoint=f"creator profile {creator_ref}",
        )
        persona_id = _required_text(
            profile,
            "personaId",
            endpoint=f"creator profile {creator_ref}",
        )
        if author_id in creators_by_author:
            raise PostApiVerificationError(f"duplicate creator authorId: {author_id}")
        avatar_asset = _object(
            profile.get("avatarAsset"),
            label=f"creator avatar binding {creator_ref}",
        )
        avatar_asset_id = _required_text(
            avatar_asset,
            "assetId",
            endpoint=f"creator avatar binding {creator_ref}",
        )
        release_avatar = _object(
            media_assets.get(avatar_asset_id),
            label=f"release avatar asset {avatar_asset_id}",
        )
        avatar_sha256 = _required_text(
            avatar_asset,
            "sha256",
            endpoint=f"creator avatar binding {creator_ref}",
        )
        public_slice_key = _required_text(
            release_avatar,
            "publicSliceKey",
            endpoint=f"release avatar asset {avatar_asset_id}",
        ).lstrip("/")
        owner_refs = release_avatar.get("ownerRefs")
        avatar_bytes = release_avatar.get("bytes")
        avatar_mime_type = str(
            release_avatar.get("contentType") or ""
        ).strip().lower()
        if (
            avatar_asset.get("kind") != "avatar"
            or release_avatar.get("kind") != "avatar"
            or release_avatar.get("sha256") != avatar_sha256
            or not public_slice_key.startswith("media/avatar/s/")
            or not isinstance(avatar_bytes, int)
            or isinstance(avatar_bytes, bool)
            or avatar_bytes <= 0
            or not avatar_mime_type.startswith("image/")
            or not isinstance(owner_refs, list)
            or f"creators/{creator_ref}" not in owner_refs
        ):
            raise PostApiVerificationError(
                f"creator avatar differs from release media authority: {creator_ref}"
            )
        creators_by_author[author_id] = CreatorProfileCase(
            creator_ref=creator_ref,
            author_id=author_id,
            persona_id=persona_id,
            avatar_asset_id=avatar_asset_id,
            avatar_url=f"{media_origin}/{public_slice_key}",
            avatar_bytes=avatar_bytes,
            avatar_sha256=avatar_sha256,
            avatar_mime_type=avatar_mime_type,
        )
    imported_authors = creator_report.get("authorIds")
    if not isinstance(imported_authors, list) or {
        str(value).strip() for value in imported_authors if str(value).strip()
    } != set(creators_by_author):
        raise PostApiVerificationError(
            "creator importer receipt does not exactly match release creator profiles"
        )
    verified_creators = creator_report.get("verifiedCreatorIds")
    if (
        creator_report.get("projectionDatabase") != "quwoquan_user"
        or not isinstance(verified_creators, list)
        or {str(value).strip() for value in verified_creators if str(value).strip()}
        != {case.creator_ref for case in creators_by_author.values()}
    ):
        raise PostApiVerificationError(
            "creator importer readback does not exactly match release creator authority"
        )
    bindings = report.get("postBindings")
    if not isinstance(bindings, list):
        raise PostApiVerificationError("post importer report lacks postBindings")
    cases: list[PostApiCase] = []
    observed: set[str] = set()
    post_ids: set[str] = set()
    for index, raw in enumerate(bindings):
        row = _object(raw, label=f"post binding {index}")
        post_ref = _normalized_post_ref(row.get("postRef"))
        if post_ref in observed:
            raise PostApiVerificationError(
                f"duplicate imported post reference: {post_ref}"
            )
        post_id = _required_text(row, "postId", endpoint=f"post binding {index}")
        if post_id in post_ids:
            raise PostApiVerificationError(f"duplicate imported post id: {post_id}")
        try:
            content_type = ContentType(
                _required_text(row, "contentType", endpoint=f"post binding {index}")
            )
        except ValueError as exc:
            raise PostApiVerificationError(
                f"post binding {index} has unsupported contentType"
            ) from exc
        if content_type is ContentType.HOMEPAGE:
            raise PostApiVerificationError("homepage is not a post API carrier")
        media_cases = tuple(
            sorted(
                (
                    _release_media_case(asset, media_origin=media_origin)
                    for asset in media_assets.values()
                    if f"posts/{post_ref}" in (asset.get("ownerRefs") or [])
                ),
                key=lambda item: item.asset_id,
            )
        )
        if content_type is not ContentType.ARTICLE and not media_cases:
            raise PostApiVerificationError(
                f"post has no release-bound media authority: {post_ref}"
            )
        cases.append(
            PostApiCase(
                post_ref=post_ref,
                post_id=post_id,
                content_type=content_type,
                author_id=_required_text(
                    row,
                    "authorId",
                    endpoint=f"post binding {index}",
                ),
                source_attribution=_source_attribution(
                    release_root,
                    post_ref,
                    content_type=content_type,
                ),
                media_assets=media_cases,
            )
        )
        observed.add(post_ref)
        post_ids.add(post_id)
    if observed != expected:
        raise PostApiVerificationError(
            "post importer bindings do not exactly match release desired state"
        )
    missing_creators = sorted(
        {case.author_id for case in cases} - set(creators_by_author)
    )
    if missing_creators:
        raise PostApiVerificationError(
            "post authors are not owned by the release creator import: "
            f"{missing_creators[:3]}"
        )
    return sorted(cases, key=lambda case: case.post_ref), creators_by_author


__all__ = [
    "CreatorProfileCase",
    "read_post_and_creator_cases",
]
