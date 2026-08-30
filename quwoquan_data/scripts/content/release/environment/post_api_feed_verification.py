"""Verify release-bound feed exposure through the public content API.

从 post_api_verification.py 逐字迁出的 feed 校验域：分页契约读取、
逐条 release 匹配、可见 feed 与 typed feed 的 release-bound 断言。
"""
from __future__ import annotations

from http import HTTPStatus
from typing import Any, Mapping

import yaml
from content.release.environment.post_api_media_verification import (
    PostApiCase,
    PostApiVerificationError,
    _object,
    _optional_text,
    _public_media_path,
    _required_text,
)
from content.release.environment.post_api_projection_verification import (
    reject_unknown_content_post_projection_fields as _reject_unknown_content_post_projection_fields,
)
from content.release.environment.post_api_release_cases import CreatorProfileCase
from content.release.environment.public_api_client import PublicApiClient
from core.control_types import ContentType
from core.paths import REPO_ROOT

CONTENT_POST_OPERATIONS_PATH = (
    REPO_ROOT
    / "quwoquan_service/services/content-service/contracts/content/post/operations.yaml"
)
FEED_PAGE_ID = "content.feed.list"


def _operation_payload(response: Any, *, endpoint: str) -> dict[str, Any]:
    operation = getattr(response, "operation", None)
    if operation is None:
        raise PostApiVerificationError(f"{endpoint} lacks request trace evidence")
    return operation.as_payload()


def _post_feed_page_limit() -> int:
    """Return GET /content/feed maximum_items from the owning operation contract."""
    try:
        document = yaml.safe_load(
            CONTENT_POST_OPERATIONS_PATH.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError) as exc:
        raise PostApiVerificationError(
            f"content post operations unreadable: {CONTENT_POST_OPERATIONS_PATH}"
        ) from exc
    if not isinstance(document, Mapping):
        raise PostApiVerificationError("content post operations must be an object")
    routes = document.get("api_routes")
    if not isinstance(routes, list):
        raise PostApiVerificationError("content post api_routes must be an array")
    for route in routes:
        if not isinstance(route, Mapping):
            continue
        if (
            str(route.get("method") or "").upper() != "GET"
            or str(route.get("path") or "") != "/content/feed"
            or str(route.get("operation") or "") != "GetFeed"
        ):
            continue
        pagination = route.get("pagination")
        if not isinstance(pagination, Mapping):
            raise PostApiVerificationError("GetFeed pagination contract is missing")
        maximum = pagination.get("maximum_items")
        if isinstance(maximum, int) and maximum > 0:
            return maximum
        raise PostApiVerificationError("GetFeed pagination.maximum_items is invalid")
    raise PostApiVerificationError("GetFeed route contract is missing")


def _feed_item_matches_release(
    item: Mapping[str, Any],
    *,
    cases_by_id: Mapping[str, PostApiCase],
    creators_by_author: Mapping[str, CreatorProfileCase],
    endpoint: str,
) -> str | None:
    _reject_unknown_content_post_projection_fields(item, endpoint=endpoint)
    post_id = _required_text(item, "postId", endpoint=endpoint)
    case = cases_by_id.get(post_id)
    if case is None:
        return None
    if _required_text(item, "contentIdentity", endpoint=endpoint) != "work":
        raise PostApiVerificationError(
            f"{endpoint} content identity mismatch for {case.post_ref}"
        )
    if _required_text(item, "authorId", endpoint=endpoint) != case.author_id:
        raise PostApiVerificationError(f"{endpoint} author mismatch for {case.post_ref}")
    creator = creators_by_author.get(case.author_id)
    if creator is None:
        raise PostApiVerificationError(
            f"{endpoint} creator closure is missing for {case.post_ref}"
        )
    if _required_text(item, "authorDisplayName", endpoint=endpoint) != creator.display_name:
        raise PostApiVerificationError(
            f"{endpoint} author display name mismatch for {case.post_ref}"
        )
    item_avatar_url = (
        _required_text(item, "authorAvatarUrl", endpoint=endpoint)
        if creator.avatar_url
        else _optional_text(item, "authorAvatarUrl", endpoint=endpoint)
    )
    if _public_media_path(item_avatar_url) != _public_media_path(creator.avatar_url):
        raise PostApiVerificationError(
            f"{endpoint} author avatar mismatch for {case.post_ref}"
        )
    if _required_text(item, "contentType", endpoint=endpoint) != case.content_type.value:
        raise PostApiVerificationError(
            f"{endpoint} content type mismatch for {case.post_ref}"
        )
    return post_id


def _verify_visible_release_feed(
    client: PublicApiClient,
    *,
    cases_by_id: Mapping[str, PostApiCase],
    creators_by_author: Mapping[str, CreatorProfileCase],
    name: str,
    query: dict[str, str],
) -> dict[str, Any]:
    response = client.get_json(
        "content/feed",
        page_id=FEED_PAGE_ID,
        query=query,
    )
    if response.status != HTTPStatus.OK:
        raise PostApiVerificationError(f"{name} feed returned non-200")
    payload = response.payload
    if not isinstance(payload, dict):
        raise PostApiVerificationError(
            f"{name} feed response payload must be an object"
        )
    object_cards = payload.get("objectCards")
    if not isinstance(object_cards, list):
        raise PostApiVerificationError(f"{name} feed lacks objectCards array")
    items = payload.get("items")
    if not isinstance(items, list):
        raise PostApiVerificationError(f"{name} feed lacks items")
    matched = sorted(
        post_id
        for index, raw in enumerate(items)
        if (
            post_id := _feed_item_matches_release(
                _object(raw, label=f"{name} feed item {index}"),
                cases_by_id=cases_by_id,
                creators_by_author=creators_by_author,
                endpoint=f"{name} feed",
            )
        )
        is not None
    )
    if not matched:
        raise PostApiVerificationError(
            f"{name} feed does not expose any release-bound postId"
        )
    canonical_query = "&".join(f"{key}={value}" for key, value in query.items())
    return {
        "name": name,
        "path": "/content/feed",
        "query": canonical_query,
        "status": response.status,
        "releaseBound": True,
        "matchedPostIds": matched,
        "requests": [_operation_payload(response, endpoint=f"{name} feed")],
    }


def _verify_typed_feed(
    client: PublicApiClient,
    cases: list[PostApiCase],
    creators_by_author: Mapping[str, CreatorProfileCase],
    *,
    include_premium_stream: bool,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    page_limit = _post_feed_page_limit()
    cases_by_id = {case.post_id: case for case in cases}
    expected_by_type: dict[ContentType, dict[str, PostApiCase]] = {}
    for case in cases:
        expected_by_type.setdefault(case.content_type, {})[case.post_id] = case
    feed_status: dict[str, int] = {}
    feed_queries = [
        _verify_visible_release_feed(
            client,
            cases_by_id=cases_by_id,
            creators_by_author=creators_by_author,
            name="discovery_work",
            query={"identity": "work", "limit": str(page_limit)},
        )
    ]
    for content_type, expected in expected_by_type.items():
        cursor = ""
        seen: set[str] = set()
        seen_cursors: set[str] = set()
        request_evidence: list[dict[str, Any]] = []
        while len(seen) < len(expected):
            query = {
                "identity": "work",
                "type": content_type.value,
                "limit": str(page_limit),
            }
            if cursor:
                query["cursor"] = cursor
            response = client.get_json(
                "content/feed",
                page_id=FEED_PAGE_ID,
                query=query,
            )
            request_evidence.append(
                _operation_payload(
                    response,
                    endpoint=f"typed {content_type.value} feed",
                )
            )
            if response.status != HTTPStatus.OK:
                raise PostApiVerificationError(
                    f"typed feed returned non-200 for {content_type.value}"
                )
            items = response.payload.get("items")
            if not isinstance(items, list):
                raise PostApiVerificationError("typed feed lacks items")
            for index, raw in enumerate(items):
                item = _object(raw, label=f"typed feed {content_type.value} item {index}")
                post_id = _feed_item_matches_release(
                    item,
                    cases_by_id=expected,
                    creators_by_author=creators_by_author,
                    endpoint=f"typed {content_type.value} feed",
                )
                if post_id is None:
                    continue
                seen.add(post_id)
                feed_status[post_id] = response.status
            next_cursor = str(response.payload.get("nextCursor") or "").strip()
            if len(seen) == len(expected):
                break
            if not next_cursor or next_cursor in seen_cursors:
                missing = sorted(set(expected) - seen)
                raise PostApiVerificationError(
                    f"typed feed omitted imported {content_type.value} posts: {missing[:3]}"
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        feed_queries.append(
            {
                "name": f"typed_{content_type.value}",
                "path": "/content/feed",
                "query": (
                    f"identity=work&type={content_type.value}&limit={page_limit}"
                ),
                "status": HTTPStatus.OK,
                "releaseBound": True,
                "matchedPostIds": sorted(seen),
                "requests": request_evidence,
            }
        )
    feed_queries.append(
        _verify_visible_release_feed(
            client,
            cases_by_id=cases_by_id,
            creators_by_author=creators_by_author,
            name="homepage_recommend",
            query={
                "sort": "recommend",
                "channelId": "recommend",
                "limit": str(page_limit),
            },
        )
    )
    if include_premium_stream:
        feed_queries.append(
            _verify_visible_release_feed(
                client,
                cases_by_id=cases_by_id,
                creators_by_author=creators_by_author,
                name="premium_stream",
                query={
                    "sort": "recommend",
                    "channelId": "premium_stream",
                    "limit": str(page_limit),
                },
            )
        )
    return feed_status, feed_queries
