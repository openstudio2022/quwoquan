"""Verify release-imported posts through the public content API."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import yaml
from content.release.environment.post_api_media_verification import (
    PostApiCase,
    PostApiVerificationError,
    _object,
    _require_media,
    _required_text,
    _verify_binary_media,
    _verify_source_attribution,
)
from content.release.environment.post_api_projection_verification import (
    reject_unknown_content_post_projection_fields as _reject_unknown_content_post_projection_fields,
)
from content.release.environment.post_api_projection_verification import (
    verify_search_projection as _verify_search_projection,
)
from content.release.environment.post_api_release_cases import (
    CreatorProfileCase,
    read_post_and_creator_cases,
)
from content.release.environment.public_api_client import (
    PublicApiClient,
    PublicApiClientError,
)
from content.release.model import DeploymentEnvironment
from core.control_types import ContentType
from core.io import write_json
from core.paths import OUTPUT_ROOT, REPO_ROOT
from core.schema import assert_valid

CONTENT_POST_OPERATIONS_PATH = (
    REPO_ROOT
    / "quwoquan_service/services/content-service/contracts/content/post/operations.yaml"
)
FEED_PAGE_ID = "content.feed.list"
POST_DETAIL_PAGE_ID = "content.post.get"
USER_PROFILE_PAGE_ID = "user.profile"


def _operation_payload(response: Any, *, endpoint: str) -> dict[str, Any]:
    operation = getattr(response, "operation", None)
    if operation is None:
        raise PostApiVerificationError(f"{endpoint} lacks request trace evidence")
    return operation.as_payload()


def _public_media_path(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _optional_text(payload: Mapping[str, Any], field: str, *, endpoint: str) -> str:
    value = payload.get(field)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise PostApiVerificationError(f"{endpoint} {field} must be a string or null")
    return value.strip()


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


def _verify_detail(
    client: PublicApiClient,
    case: PostApiCase,
    creator: CreatorProfileCase,
) -> dict[str, Any]:
    response = client.get_json(
        f"content/posts/{quote(case.post_id, safe='')}",
        page_id=POST_DETAIL_PAGE_ID,
    )
    if response.status != HTTPStatus.OK:
        raise PostApiVerificationError(f"post detail returned non-200 for {case.post_ref}")
    payload = response.payload
    if _required_text(payload, "postId", endpoint="post detail") != case.post_id:
        raise PostApiVerificationError(f"post detail id mismatch for {case.post_ref}")
    if _required_text(payload, "authorId", endpoint="post detail") != case.author_id:
        raise PostApiVerificationError(f"post detail author mismatch for {case.post_ref}")
    if (
        _required_text(payload, "authorDisplayName", endpoint="post detail")
        != creator.display_name
    ):
        raise PostApiVerificationError(
            f"post detail author display name mismatch for {case.post_ref}"
        )
    detail_avatar_url = (
        _required_text(payload, "authorAvatarUrl", endpoint="post detail")
        if creator.avatar_url
        else _optional_text(payload, "authorAvatarUrl", endpoint="post detail")
    )
    if _public_media_path(detail_avatar_url) != _public_media_path(creator.avatar_url):
        raise PostApiVerificationError(
            f"post detail author avatar mismatch for {case.post_ref}"
        )
    if _required_text(payload, "contentType", endpoint="post detail") != case.content_type.value:
        raise PostApiVerificationError(f"post detail content type mismatch for {case.post_ref}")
    if _required_text(payload, "contentIdentity", endpoint="post detail") != "work":
        raise PostApiVerificationError(f"post detail content identity mismatch for {case.post_ref}")
    media_urls, cover_url, video_url = _require_media(payload, case.content_type)
    _verify_source_attribution(payload, case)
    observed_urls = {url for url in (*media_urls, cover_url, video_url) if url}
    expected_urls = {asset.public_url for asset in case.media_assets}
    if case.content_type is not ContentType.ARTICLE and observed_urls != expected_urls:
        raise PostApiVerificationError(
            f"post media URLs drift from release authority for {case.post_ref}"
        )
    probes: list[dict[str, Any]] = []
    for asset in case.media_assets:
        full_identity = asset.kind == "image"
        probe = _verify_binary_media(
            client,
            asset.public_url,
            expected_kind="video" if asset.kind == "video" else "image",
            expected_bytes=asset.expected_bytes if full_identity else 0,
            expected_sha256=asset.expected_sha256 if full_identity else "",
            expected_mime_type=asset.expected_mime_type,
        )
        probes.append(
            {
                "assetId": asset.asset_id,
                "kind": asset.kind,
                "expectedBytes": asset.expected_bytes,
                "expectedSha256": asset.expected_sha256,
                **probe,
            }
        )
    return {
        "detailStatus": response.status,
        "mediaReady": case.content_type is ContentType.ARTICLE or bool(probes),
        "mediaProbeCount": len(probes),
        "mediaProbes": probes,
        "sourceAttributionReady": True,
    }


def _verify_author_profile(
    client: PublicApiClient,
    creator: CreatorProfileCase,
) -> dict[str, Any]:
    response = client.get_json(
        f"user/{quote(creator.persona_id, safe='')}",
        page_id=USER_PROFILE_PAGE_ID,
    )
    if response.status != HTTPStatus.OK:
        raise PostApiVerificationError(
            "creator public profile returned "
            f"status={response.status} for canonical "
            f"personaId={creator.persona_id} ({creator.creator_ref})"
        )
    if _required_text(response.payload, "personaId", endpoint="creator public profile") != creator.persona_id:
        raise PostApiVerificationError(
            f"creator public profile identity mismatch for {creator.creator_ref}"
        )
    if _required_text(response.payload, "displayName", endpoint="creator public profile") == "":
        raise PostApiVerificationError(
            f"creator public profile lacks display name for {creator.creator_ref}"
        )
    avatar_url = _optional_text(
        response.payload,
        "avatarUrl",
        endpoint="creator public profile",
    )
    # Persona public profiles append ?v=<avatarVersion> for cache busting; the
    # release authority binds the public slice path without that query.
    if _public_media_path(avatar_url) != _public_media_path(creator.avatar_url):
        raise PostApiVerificationError(
            f"creator public avatar URL drift for {creator.creator_ref}"
        )
    if creator.avatar_asset_id is None:
        if avatar_url:
            raise PostApiVerificationError(
                f"creator public avatar unexpectedly exists for {creator.creator_ref}"
            )
        return {
            "creatorRef": creator.creator_ref,
            "authorId": creator.author_id,
            "personaId": creator.persona_id,
            "profileStatus": response.status,
            "avatarAssetId": None,
            "avatarUrl": "",
            "avatarMediaReady": False,
            "avatarProbeCount": 0,
            "avatarProbe": None,
            "usesPlatformDefaultAvatar": True,
        }
    if (
        creator.avatar_bytes is None
        or creator.avatar_sha256 is None
        or creator.avatar_mime_type is None
    ):
        raise PostApiVerificationError(
            f"creator avatar authority is incomplete for {creator.creator_ref}"
        )
    avatar_probe = _verify_binary_media(
        client,
        avatar_url,
        expected_kind="image",
        expected_bytes=creator.avatar_bytes,
        expected_sha256=creator.avatar_sha256,
        expected_mime_type=creator.avatar_mime_type,
    )
    return {
        "creatorRef": creator.creator_ref,
        "authorId": creator.author_id,
        "personaId": creator.persona_id,
        "profileStatus": response.status,
        "avatarAssetId": creator.avatar_asset_id,
        "avatarUrl": avatar_url,
        "avatarMediaReady": True,
        "avatarProbeCount": 1,
        "avatarProbe": avatar_probe,
        "usesPlatformDefaultAvatar": False,
    }


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


def write_post_api_verification(
    *,
    environment: DeploymentEnvironment,
    release_id: str,
    run_id: str,
    release_root: Path,
    importer_report_path: Path,
    creator_importer_report_path: Path,
    output_path: Path,
    api_base_url: str,
    media_delivery_base_url: str,
    ssl_cafile: str = "",
    readiness_phase: str = "commercial",
) -> Path:
    """Write schema-validated, release-bound public post API evidence."""
    if readiness_phase not in {"research", "consumer", "commercial"}:
        raise PostApiVerificationError(
            "post API verification readiness_phase must be research, consumer or commercial"
        )
    if readiness_phase == "research":
        raise PostApiVerificationError(
            "DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE: GATE_BLOCK research "
            "API verification requires a protected, "
            "whitelisted internal identity adapter; anonymous guest access "
            "cannot be reused as research evidence"
        )
    try:
        cases, creators_by_author = read_post_and_creator_cases(
            environment=environment,
            release_id=release_id,
            release_root=release_root,
            importer_report_path=importer_report_path,
            creator_importer_report_path=creator_importer_report_path,
            media_delivery_base_url=media_delivery_base_url,
        )
        unauthenticated_client = PublicApiClient(
            base_url=api_base_url,
            ssl_cafile=ssl_cafile,
        )
        guest = unauthenticated_client.login_fresh_guest()
        client = unauthenticated_client.for_guest(guest)
        feed_status, feed_queries = _verify_typed_feed(
            client,
            cases,
            creators_by_author,
            include_premium_stream=readiness_phase in {"research", "commercial"},
        )
        creator_rows = [
            _verify_author_profile(client, creator)
            for creator in sorted(
                creators_by_author.values(),
                key=lambda item: item.creator_ref,
            )
        ]
        creator_status_by_author = {
            str(row["authorId"]): int(row["profileStatus"])
            for row in creator_rows
        }
        search_queries = _verify_search_projection(
            client,
            release_root=release_root,
            cases=cases,
            creators_by_author=creators_by_author,
        )
        rows = []
        for case in cases:
            detail = _verify_detail(client, case, creators_by_author[case.author_id])
            rows.append(
                {
                    "postRef": case.post_ref,
                    "postId": case.post_id,
                    "contentType": case.content_type.value,
                    "authorId": case.author_id,
                    "detailStatus": detail["detailStatus"],
                    "feedStatus": feed_status[case.post_id],
                    "mediaReady": detail["mediaReady"],
                    "mediaProbeCount": detail["mediaProbeCount"],
                    "mediaProbes": detail["mediaProbes"],
                    "sourceAttributionReady": detail["sourceAttributionReady"],
                    "authorProfileStatus": creator_status_by_author[case.author_id],
                }
            )
    except PublicApiClientError as exc:
        raise PostApiVerificationError(str(exc)) from exc
    try:
        importer_ref = importer_report_path.relative_to(OUTPUT_ROOT).as_posix()
        creator_importer_ref = creator_importer_report_path.relative_to(OUTPUT_ROOT).as_posix()
    except ValueError as exc:
        raise PostApiVerificationError("post importer report must be below QWQ_OUTPUT_ROOT") from exc
    payload = {
        "schema": "quwoquan_data.post_api_verification",
        "environment": environment.value,
        "releaseId": release_id,
        "runId": run_id,
        "readinessPhase": readiness_phase,
        "sourceImportReportRef": importer_ref,
        "creatorImportReportRef": creator_importer_ref,
        "apiBaseUrl": api_base_url.rstrip("/"),
        "mediaDeliveryBaseUrl": media_delivery_base_url.rstrip("/"),
        "guestActorHash": guest.guest_actor_hash,
        "guestLogin": guest.login_operation.as_payload(),
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "passed": True,
        "feedQueries": feed_queries,
        "searchQueries": search_queries,
        "creators": creator_rows,
        "posts": rows,
        "issues": [],
    }
    try:
        assert_valid(payload, "release", "post_api_verification", label="post_api_verification")
    except (TypeError, ValueError) as exc:
        raise PostApiVerificationError(str(exc)) from exc
    if output_path.exists():
        raise PostApiVerificationError(f"post API verification already exists: {output_path}")
    write_json(output_path, payload)
    return output_path


__all__ = ["PostApiVerificationError", "write_post_api_verification"]
