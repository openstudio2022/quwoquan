"""Project canonical App UAT identities from an immutable Data release."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.io import read_json
from core.release_layout import payload_file


class AppUatEnvelopeError(ValueError):
    """The release closure cannot supply one exact App UAT identity."""


def _object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise AppUatEnvelopeError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, Mapping):
        raise AppUatEnvelopeError(f"{label} must be an object: {path}")
    return dict(value)


def _required_text(value: object, *, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise AppUatEnvelopeError(f"{label} must be non-empty")
    return result


def _normalized_ref(value: object, *, kind: str) -> str:
    result = str(value or "").strip().strip("/")
    prefixes = {
        "entities": ("entities/", "entity/"),
        "posts": ("posts/", "post/"),
        "creators": ("creators/", "creator/"),
        "tags": ("tags/", "tag/"),
    }
    if kind not in prefixes:
        raise AppUatEnvelopeError(f"unsupported release object kind: {kind}")
    for prefix in prefixes[kind]:
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break
    if not result:
        raise AppUatEnvelopeError(f"release {kind} ref must be non-empty")
    return result


def _release_object(
    release_root: Path,
    *,
    kind: str,
    ref: str,
    filename: str,
    label: str,
) -> dict[str, Any]:
    normalized = _normalized_ref(ref, kind=kind)
    return _object(
        payload_file(release_root, f"objects/{kind}/{normalized}/{filename}"),
        label=label,
    )


def _homepage_identity(
    *,
    release_root: Path,
    entity_refs: list[str],
    homepage_report: Mapping[str, Any],
) -> tuple[str, str]:
    homepage_rows = {
        _normalized_ref(row.get("entityRef"), kind="entities"): row
        for row in homepage_report.get("entities") or []
        if isinstance(row, Mapping)
    }
    candidates = []
    for ref in entity_refs:
        normalized = _normalized_ref(ref, kind="entities")
        candidates.append((normalized, homepage_rows.get(normalized)))
    candidates = [(ref, row) for ref, row in candidates if row is not None]
    if not candidates:
        raise AppUatEnvelopeError("appUatEnvelope lacks a release-bound homepage")
    homepage_ref, homepage_row = candidates[0]
    entity = _release_object(
        release_root,
        kind="entities",
        ref=homepage_ref,
        filename="_entity.json",
        label=f"release entity {homepage_ref}",
    )
    if _normalized_ref(entity.get("entityRef"), kind="entities") != homepage_ref:
        raise AppUatEnvelopeError(
            "appUatEnvelope homepage entityRef drifts from release object"
        )
    title = _required_text(entity.get("label"), label="release homepage title")
    if _required_text(homepage_row.get("title"), label="verified homepage title") != title:
        raise AppUatEnvelopeError(
            "appUatEnvelope homepage title drifts from release object"
        )
    return (
        _required_text(homepage_row.get("homepageId"), label="verified homepageId"),
        title,
    )


def _post_candidates(
    *,
    release_root: Path,
    post_refs: list[str],
    bindings: list[object],
    queries_by_name: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[tuple[str, str, dict[str, Any]]]]:
    binding_by_ref = {
        _normalized_ref(row.get("postRef"), kind="posts"): row
        for row in bindings
        if isinstance(row, Mapping)
    }
    query_ids = {
        name: {
            _required_text(item, label=f"{name} matched postId")
            for item in row.get("matchedPostIds") or []
        }
        for name, row in queries_by_name.items()
    }
    candidates: dict[str, list[tuple[str, str, dict[str, Any]]]] = {
        "article": [],
        "image": [],
        "video": [],
    }
    for raw_ref in post_refs:
        post_ref = _normalized_ref(raw_ref, kind="posts")
        binding = binding_by_ref.get(post_ref)
        if binding is None:
            raise AppUatEnvelopeError(
                f"appUatEnvelope post lacks import binding: {post_ref}"
            )
        manifest = _release_object(
            release_root,
            kind="posts",
            ref=post_ref,
            filename="manifest.json",
            label=f"release post manifest {post_ref}",
        )
        content_type = _required_text(
            manifest.get("contentType"), label=f"release post contentType {post_ref}"
        )
        if content_type not in candidates:
            continue
        if manifest.get("contentIdentity") != "work":
            raise AppUatEnvelopeError(
                f"appUatEnvelope post contentIdentity is not work: {post_ref}"
            )
        if binding.get("contentType") != content_type:
            raise AppUatEnvelopeError(
                f"appUatEnvelope post contentType drifts from import binding: {post_ref}"
            )
        manifest_author = _required_text(
            manifest.get("authorId"), label=f"release authorId {post_ref}"
        )
        if (
            _required_text(
                binding.get("authorId"), label=f"import authorId {post_ref}"
            )
            != manifest_author
        ):
            raise AppUatEnvelopeError(
                f"appUatEnvelope post authorId drifts from import binding: {post_ref}"
            )
        post_id = _required_text(
            binding.get("postId"), label=f"import postId {post_ref}"
        )
        if post_id in query_ids.get(f"typed_{content_type}", set()):
            candidates[content_type].append((post_ref, post_id, manifest))
    return candidates


def _creator_name(
    *,
    release_root: Path,
    creator_ids: list[str],
    article: Mapping[str, Any],
) -> str:
    author_id = _required_text(article.get("authorId"), label="release article authorId")
    matches = []
    for creator_ref in creator_ids:
        profile = _release_object(
            release_root,
            kind="creators",
            ref=creator_ref,
            filename="profile.json",
            label=f"release creator profile {creator_ref}",
        )
        if profile.get("authorId") == author_id:
            matches.append(profile)
    if len(matches) != 1:
        raise AppUatEnvelopeError(
            "appUatEnvelope article author must map to exactly one release creator"
        )
    return _required_text(
        matches[0].get("displayName"), label="release creator displayName"
    )


def _tag_label(
    *,
    release_root: Path,
    tag_refs: list[str],
    article: Mapping[str, Any],
) -> str:
    article_tags = {
        _normalized_ref(item, kind="tags")
        for item in article.get("tagRefs") or []
        if str(item or "").strip()
    }
    desired_tags = {_normalized_ref(item, kind="tags") for item in tag_refs}
    matches = sorted(article_tags & desired_tags)
    if not matches:
        raise AppUatEnvelopeError("appUatEnvelope article lacks a release-bound tag")
    tag = _release_object(
        release_root,
        kind="tags",
        ref=matches[0],
        filename="_definition.json",
        label=f"release tag definition {matches[0]}",
    )
    return _required_text(tag.get("label"), label="release tag label")


def build_app_uat_envelope(
    *,
    release_root: Path,
    release_id: str,
    entity_refs: list[str],
    post_refs: list[str],
    creator_ids: list[str],
    tag_refs: list[str],
    bindings: list[object],
    homepage_report: Mapping[str, Any],
    queries_by_name: Mapping[str, Mapping[str, Any]],
    verified_playable_video_ids: set[str],
    release_class: str,
    product_lifecycle_state: str,
) -> dict[str, str]:
    """Project exact canonical App UAT fields from release objects and readbacks."""

    homepage_id, homepage_title = _homepage_identity(
        release_root=release_root,
        entity_refs=entity_refs,
        homepage_report=homepage_report,
    )
    query_ids = {
        name: set(row.get("matchedPostIds") or [])
        for name, row in queries_by_name.items()
    }
    candidates = _post_candidates(
        release_root=release_root,
        post_refs=post_refs,
        bindings=bindings,
        queries_by_name=queries_by_name,
    )
    articles = [
        row
        for row in candidates["article"]
        if row[1] in query_ids.get("homepage_recommend", set())
    ]
    images = candidates["image"]
    videos = [
        row
        for row in candidates["video"]
        if row[1] in query_ids.get("premium_stream", set())
        and row[1] in verified_playable_video_ids
    ]
    if not articles or not images or not videos:
        raise AppUatEnvelopeError(
            "appUatEnvelope lacks exact-query-bound article/image/Premium playable video"
        )
    article_ref, article_id, article = articles[0]
    _image_ref, image_id, image = images[0]
    _video_ref, video_id, video = videos[0]
    attribution = video.get("sourceAttribution")
    if not isinstance(attribution, Mapping):
        raise AppUatEnvelopeError(
            "appUatEnvelope video sourceAttribution must be an object"
        )
    return {
        "releaseId": _required_text(release_id, label="releaseId"),
        "releaseClass": _required_text(release_class, label="releaseClass"),
        "productLifecycleState": _required_text(
            product_lifecycle_state,
            label="productLifecycleState",
        ),
        "homepageId": homepage_id,
        "homepageTitle": homepage_title,
        "articleWorkId": article_id,
        "articleTitle": _required_text(
            article.get("publishTitle") or article.get("title"),
            label=f"release article title {article_ref}",
        ),
        "imageWorkId": image_id,
        "imageTitle": _required_text(
            image.get("publishTitle") or image.get("title"),
            label="release image title",
        ),
        "videoWorkId": video_id,
        "creatorName": _creator_name(
            release_root=release_root, creator_ids=creator_ids, article=article
        ),
        "tagLabel": _tag_label(
            release_root=release_root, tag_refs=tag_refs, article=article
        ),
        "videoAttribution": _required_text(
            attribution.get("attributionText"), label="release video attribution"
        ),
    }


__all__ = ["AppUatEnvelopeError", "build_app_uat_envelope"]
