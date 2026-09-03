"""环境集成探针的响应语义判定（从 run_environment_integration_probe 迁出）。

纯函数族：feed/搜索/作者主页/release 样本响应的契约语义校验，以及
ContentPostProjection 字段闭集加载。probe 主模块经模块属性访问消费并
re-export 全部符号（测试以 `probe._xxx` 直读语义函数做行为断言）。
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]

CONTENT_POST_PROJECTION_PATH = (
    REPO_ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "contracts"
    / "content"
    / "post"
    / "projections"
    / "content_post_projection.yaml"
)


def _content_post_projection_fields() -> frozenset[str]:
    """Load public feed-item keys from the canonical projection contract."""
    try:
        document = yaml.safe_load(
            CONTENT_POST_PROJECTION_PATH.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(
            "canonical ContentPostProjection contract is unreadable: "
            f"{CONTENT_POST_PROJECTION_PATH}"
        ) from exc
    if (
        not isinstance(document, dict)
        or document.get("read_model") != "ContentPostProjection"
    ):
        raise ValueError("canonical ContentPostProjection contract has invalid read_model")
    raw_fields = document.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise ValueError(
            "canonical ContentPostProjection contract fields must be a non-empty array"
        )
    fields: set[str] = set()
    for index, raw_field in enumerate(raw_fields):
        if not isinstance(raw_field, dict):
            raise ValueError(
                f"canonical ContentPostProjection field {index} must be an object"
            )
        name = str(raw_field.get("name") or "").strip()
        if not name or name in fields:
            raise ValueError(
                f"canonical ContentPostProjection field {index} has invalid name"
            )
        fields.add(name)
    return frozenset(fields)



def _content_feed_semantic_issue(payload: str) -> tuple[str | None, int | None]:
    issue, count, _post_ids = _content_feed_semantic_result(payload)
    return issue, count


def _research_anonymous_convergence_issue(
    payload: str,
) -> tuple[str | None, int | None]:
    """Assert the anonymous feed converges to the research-isolation empty page.

    research release 的匿名读回必须是 DEC-032 收敛结果：items 为空、
    outcome=empty、emptyReason=no_active_release，且不回显 releaseId/
    manifestDigest。任何一条内容或任何 release 身份在场即隔离泄露。
    """
    body = payload.strip()
    if not body:
        return "response body is empty", 0
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", None
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", None
    items = decoded.get("items")
    if not isinstance(items, list):
        return 'response payload is missing array "items"', None
    if items:
        return (
            "research isolation leak: anonymous feed returned "
            f"{len(items)} item(s) instead of the no_active_release empty page",
            len(items),
        )
    outcome = str(decoded.get("outcome") or "")
    if outcome != "empty":
        return f'research convergence expects outcome "empty", got "{outcome}"', 0
    empty_reason = str(decoded.get("emptyReason") or "")
    if empty_reason != "no_active_release":
        return (
            'research convergence expects emptyReason "no_active_release", '
            f'got "{empty_reason}"',
            0,
        )
    leaked_identity = sorted(
        key
        for key in ("releaseId", "manifestDigest")
        if str(decoded.get(key) or "").strip()
    )
    if leaked_identity:
        return (
            "research isolation leak: anonymous empty page echoes release "
            "identity field(s): " + ", ".join(leaked_identity),
            0,
        )
    return None, 0


def _content_feed_semantic_result(
    payload: str,
    *,
    expected_post_ids: set[str] | None = None,
) -> tuple[str | None, int | None, set[str]]:
    body = payload.strip()
    if not body:
        return "response body is empty", 0, set()
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", None, set()
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", None, set()
    object_cards = decoded.get("objectCards")
    if not isinstance(object_cards, list):
        return 'response payload is missing array "objectCards"', None, set()
    items: list[Any] | None = None
    candidate_items = decoded.get("items")
    if isinstance(candidate_items, list):
        items = candidate_items
    if items is None:
        return None, None, set()
    if not items:
        return 'response payload has empty "items"', 0, set()
    try:
        allowed_item_fields = _content_post_projection_fields()
    except ValueError as exc:
        return str(exc), None, set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return f"response items[{index}] must be a JSON object", None, set()
        unknown = sorted(set(item) - allowed_item_fields)
        if unknown:
            return (
                f"response items[{index}] has unknown ContentPostProjection fields: "
                + ", ".join(unknown),
                None,
                set(),
            )
    returned_post_ids = {
        str(item.get("postId") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("postId") or "").strip()
    }
    expected = {
        str(item).strip() for item in (expected_post_ids or set()) if str(item).strip()
    }
    if expected and not returned_post_ids.intersection(expected):
        return (
            "response has no postId bound to the expected immutable release",
            len(items),
            returned_post_ids,
        )
    return None, len(items), returned_post_ids


def _expected_release_post_ids(args: argparse.Namespace, check_name: str) -> set[str]:
    argument_names = {
        "content_feed": "expected_discovery_post_id",
        "homepage_recommend": "expected_homepage_recommend_post_id",
        "video_book_feed": "expected_video_post_id",
        "premium_feed": "expected_premium_video_post_id",
    }
    argument_name = argument_names.get(check_name)
    if argument_name is None:
        return set()
    return {
        str(item).strip()
        for item in getattr(args, argument_name, [])
        if str(item).strip()
    }


AUTHOR_POSTS_CHECK_NAME = "author_posts_contract"
CREATOR_PROFILE_CHECK_NAME = "release_creator_profile"
FEED_MEDIA_SLICES_CHECK_NAME = "feed_media_slices"
SIGNED_MEDIA_CHECK_NAME = "release_signed_media"
PRIVATE_FEED_CHECK_NAMES = frozenset(
    {"content_feed", "homepage_recommend", "video_book_feed", "premium_feed"}
)
FEED_MEDIA_SOURCE_CHECK_NAMES = PRIVATE_FEED_CHECK_NAMES


def _media_origin(media_image_base_url: str) -> str:
    """media base（…/media/image）所在的 scheme://host[:port] origin。"""
    parsed = urllib.parse.urlsplit(str(media_image_base_url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _feed_media_slice_urls(payload: str, media_origin: str) -> dict[str, str]:
    """从 feed 响应 items 收集全部公开媒体 slice 的绝对 URL（url -> kind）。

    feed 卡「部分图片灰/视频黑屏」的常见根因是 media-edge 缺对象；items 非空
    不等于媒体字节可读，必须逐 slice 读回验证。
    """
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    items = decoded.get("items")
    if not isinstance(items, list):
        return {}
    urls: dict[str, str] = {}

    def _add(raw: object, kind: str) -> None:
        value = str(raw or "").strip()
        if not value:
            return
        if value.startswith(("http://", "https://")):
            absolute = value
        else:
            absolute = f"{media_origin}/{value.lstrip('/')}"
        urls.setdefault(absolute, kind)

    for item in items:
        if not isinstance(item, dict):
            continue
        media_urls = item.get("mediaUrls")
        if isinstance(media_urls, list):
            for raw in media_urls:
                _add(raw, "image")
        _add(item.get("coverUrl"), "image")
        _add(item.get("thumbnailUrl"), "image")
        _add(item.get("videoUrl"), "video")
    return urls


def _author_posts_semantic_result(payload: str) -> tuple[str | None, int | None]:
    """校验 ListUserPosts 真实 wire 是 AuthorPostPageSlice/ContentPostProjection
    契约子集。App generated decoder reject unknown fields：任何契约外字段都会让
    作者主页「记录」整页解码失败，因此这里 fail-closed。"""

    body = payload.strip()
    if not body:
        return "response body is empty", None
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", None
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", None
    allowed_page_fields = {"items", "nextCursor", "hasMore"}
    unknown_page = sorted(set(decoded) - allowed_page_fields)
    if unknown_page:
        return (
            "response has unknown AuthorPostPageSlice fields: "
            + ", ".join(unknown_page),
            None,
        )
    items = decoded.get("items")
    if not isinstance(items, list):
        return 'response payload is missing array "items"', None
    if not items:
        return 'response payload has empty "items"', 0
    try:
        allowed_item_fields = _content_post_projection_fields()
    except ValueError as exc:
        return str(exc), None
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return f"response items[{index}] must be a JSON object", None
        unknown = sorted(set(item) - allowed_item_fields)
        if unknown:
            return (
                f"response items[{index}] has unknown ContentPostProjection fields: "
                + ", ".join(unknown),
                None,
            )
        if not str(item.get("postId") or "").strip():
            return f"response items[{index}] is missing postId", None
    return None, len(items)


def _search_semantic_issue(
    payload: str,
    *,
    expected_object_type: str = "",
    expected_object_id: str = "",
) -> tuple[str | None, int | None]:
    body = payload.strip()
    if not body:
        return "response body is empty", None
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", None
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", None
    request_id = decoded.get("requestId")
    if not isinstance(request_id, str) or not request_id.strip():
        return 'response payload is missing non-empty "requestId"', None
    hits = decoded.get("hits")
    if not isinstance(hits, list):
        return 'response payload is missing array "hits"', None
    expected_type = expected_object_type.strip()
    expected_id = expected_object_id.strip()
    if expected_type and expected_id and not any(
        isinstance(hit, dict)
        and str(hit.get("objectType") or "").strip() == expected_type
        and str(hit.get("objectId") or "").strip() == expected_id
        for hit in hits
    ):
        return (
            "response has no exact release-bound "
            f"{expected_type}/{expected_id} hit",
            len(hits),
        )
    return None, len(hits)


def _media_delivery_identity(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urllib.parse.urlsplit(text)
    path = parsed.path if parsed.scheme or parsed.netloc else text.partition("?")[0]
    return path.strip().lstrip("/")


def _release_sample_semantic_result(
    payload: str,
    *,
    carrier: str,
    read_object_id: str,
    expected_content_type: str,
    expected_author_id: str = "",
    expected_author_display_name: str = "",
    expected_avatar_delivery_ref: str = "",
) -> tuple[str | None, str, str]:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", "", ""
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", "", ""
    id_field = "homepageId" if carrier == "homepage" else "postId"
    returned_id = str(decoded.get(id_field) or "").strip()
    returned_type = (
        "" if carrier == "homepage" else str(decoded.get("contentType") or "").strip()
    )
    if returned_id != read_object_id:
        return f"response {id_field} is not the exact release sample", returned_id, returned_type
    if carrier != "homepage" and returned_type != expected_content_type:
        return "response contentType is not the exact release sample type", returned_id, returned_type
    if expected_author_id and str(decoded.get("authorId") or "").strip() != expected_author_id:
        return "response authorId is not the exact release creator", returned_id, returned_type
    if (
        expected_author_display_name
        and str(decoded.get("authorDisplayName") or "").strip()
        != expected_author_display_name
    ):
        return (
            "response authorDisplayName is not the exact release creator",
            returned_id,
            returned_type,
        )
    observed_avatar = _media_delivery_identity(decoded.get("authorAvatarUrl"))
    expected_avatar = _media_delivery_identity(expected_avatar_delivery_ref)
    if expected_avatar and observed_avatar != expected_avatar:
        return (
            "response authorAvatarUrl is not the exact release avatar asset",
            returned_id,
            returned_type,
        )
    return None, returned_id, returned_type


def _release_creator_profile_semantic_result(
    payload: str,
    *,
    expected_persona_id: str,
    expected_display_name: str,
    expected_avatar_delivery_ref: str,
) -> tuple[str | None, str, str]:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        return f"response body is not valid JSON: {exc.msg}", "", ""
    if not isinstance(decoded, dict):
        return "response payload must be a JSON object", "", ""
    persona_id = str(decoded.get("personaId") or "").strip()
    avatar_ref = _media_delivery_identity(decoded.get("avatarUrl"))
    if persona_id != expected_persona_id:
        return "response personaId is not the exact release creator", persona_id, avatar_ref
    if str(decoded.get("displayName") or "").strip() != expected_display_name:
        return "response displayName is not the exact release creator", persona_id, avatar_ref
    if avatar_ref != _media_delivery_identity(expected_avatar_delivery_ref):
        return "response avatarUrl is not the exact release avatar asset", persona_id, avatar_ref
    return None, persona_id, avatar_ref
