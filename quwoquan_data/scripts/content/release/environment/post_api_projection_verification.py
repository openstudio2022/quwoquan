"""Verify release-owned feed and search public projections."""
from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from http import HTTPStatus
from pathlib import Path
from typing import Any

import yaml
from content.release.environment.post_api_media_verification import (
    PostApiCase,
    PostApiVerificationError,
    _object,
)
from content.release.environment.post_api_release_cases import CreatorProfileCase
from content.release.environment.public_api_client import PublicApiClient
from core.io import read_json
from core.paths import REPO_ROOT

CONTENT_POST_PROJECTION_PATH = REPO_ROOT / (
    "quwoquan_service/services/content-service/contracts/content/post/projections/"
    "content_post_projection.yaml"
)
SEARCH_PAGE_ID = "search.global"
_SEARCH_OBJECT_TYPES = {
    "article": "article",
    "image": "photo",
    "video": "video",
}


def _operation_payload(response: Any, *, endpoint: str) -> dict[str, Any]:
    operation = getattr(response, "operation", None)
    if operation is None:
        raise PostApiVerificationError(f"{endpoint} lacks request trace evidence")
    return operation.as_payload()


@lru_cache(maxsize=1)
def _content_post_projection_fields() -> frozenset[str]:
    """Load the public feed-item keys from the canonical projection contract."""
    try:
        document = yaml.safe_load(
            CONTENT_POST_PROJECTION_PATH.read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError) as exc:
        raise PostApiVerificationError(
            "canonical ContentPostProjection contract is unreadable: "
            f"{CONTENT_POST_PROJECTION_PATH}"
        ) from exc
    if (
        not isinstance(document, Mapping)
        or document.get("read_model") != "ContentPostProjection"
    ):
        raise PostApiVerificationError(
            "canonical ContentPostProjection contract has invalid read_model"
        )
    raw_fields = document.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise PostApiVerificationError(
            "canonical ContentPostProjection contract fields must be a non-empty array"
        )
    fields: set[str] = set()
    for index, raw_field in enumerate(raw_fields):
        if not isinstance(raw_field, Mapping):
            raise PostApiVerificationError(
                f"canonical ContentPostProjection field {index} must be an object"
            )
        name = str(raw_field.get("name") or "").strip()
        if not name or name in fields:
            raise PostApiVerificationError(
                f"canonical ContentPostProjection field {index} has invalid name"
            )
        fields.add(name)
    return frozenset(fields)


def reject_unknown_content_post_projection_fields(
    item: Mapping[str, Any],
    *,
    endpoint: str,
) -> None:
    unknown = sorted(set(item) - _content_post_projection_fields())
    if unknown:
        raise PostApiVerificationError(
            f"{endpoint} item has unknown ContentPostProjection fields: "
            + ", ".join(unknown)
        )


def _search_object_type(content_type: str) -> str:
    try:
        return _SEARCH_OBJECT_TYPES[content_type]
    except KeyError as exc:
        raise PostApiVerificationError(
            f"unsupported Content search projection type: {content_type}"
        ) from exc


def _safe_evidence_value(value: object, *, default: str = "none") -> str:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 128:
        return default
    if not all(character.isalnum() or character in "._:-" for character in candidate):
        return default
    return candidate


def _search_failure_message(
    response: Any,
    *,
    query: str,
    object_types: list[str],
) -> str:
    operation = getattr(response, "operation", None)
    if operation is None:
        raise PostApiVerificationError("search lacks request trace evidence")
    status = int(getattr(response, "status", 0) or 0)
    payload = getattr(response, "payload", {})
    raw_code = payload.get("code") if isinstance(payload, Mapping) else None
    canonical_error_code = _safe_evidence_value(raw_code)
    outcome = "http_error" if status != HTTPStatus.OK else "empty"
    target_types = ",".join(
        _safe_evidence_value(value, default="invalid") for value in object_types
    )
    return (
        "Search verification failed: "
        f"outcome={outcome} status={status} "
        f"canonicalErrorCode={canonical_error_code} "
        f"requestId={_safe_evidence_value(operation.request_id)} "
        f"traceId={_safe_evidence_value(operation.trace_id)} "
        "requestSummary="
        f"method=POST,path=/search,pageId={SEARCH_PAGE_ID},"
        f"queryChars={len(query)},objectTypes={target_types},idsCount=1,limit=20"
    )


def _search_hits(
    client: PublicApiClient,
    *,
    query: str,
    object_types: list[str],
    object_id: str,
) -> dict[str, Any]:
    response = client.post_json(
        "search",
        page_id=SEARCH_PAGE_ID,
        body={
            "query": query,
            "mode": "result",
            "objectTypes": object_types,
            "ids": [object_id],
            "limit": 20,
        },
        session_header_name="X-Session-Id",
    )
    hits = response.payload.get("hits")
    matched = (
        sorted(
            {
                str(row.get("objectId") or "").strip()
                for row in hits or []
                if isinstance(row, Mapping)
                and str(row.get("objectId") or "").strip()
            }
        )
        if isinstance(hits, list)
        else []
    )
    if response.status != HTTPStatus.OK or object_id not in matched:
        raise PostApiVerificationError(
            _search_failure_message(
                response,
                query=query,
                object_types=object_types,
            )
        )
    return {
        "query": query,
        "status": response.status,
        "matchedObjectIds": matched,
        "request": _operation_payload(response, endpoint="search"),
    }


def verify_search_projection(
    client: PublicApiClient,
    *,
    release_root: Path,
    cases: list[PostApiCase],
    creators_by_author: Mapping[str, CreatorProfileCase],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        manifest_path = (
            release_root
            / "payload"
            / "objects"
            / "posts"
            / case.post_ref
            / "manifest.json"
        )
        try:
            manifest = _object(
                read_json(manifest_path),
                label=f"search post manifest {case.post_ref}",
            )
        except (OSError, TypeError, ValueError) as exc:
            raise PostApiVerificationError(
                f"search post manifest is unreadable for {case.post_ref}: {exc}"
            ) from exc
        query = str(
            manifest.get("title")
            or manifest.get("publishTitle")
            or manifest.get("caption")
            or case.post_id
        ).strip()
        proof = _search_hits(
            client,
            query=query,
            object_types=[_search_object_type(case.content_type.value)],
            object_id=case.post_id,
        )
        rows.append(
            {
                "targetType": "post",
                "targetId": case.post_id,
                **proof,
            }
        )
    for creator in sorted(
        creators_by_author.values(),
        key=lambda item: item.creator_ref,
    ):
        proof = _search_hits(
            client,
            query=creator.display_name,
            object_types=["user"],
            object_id=creator.persona_id,
        )
        rows.append(
            {
                "targetType": "author",
                "targetId": creator.persona_id,
                **proof,
            }
        )
    return rows


__all__ = [
    "reject_unknown_content_post_projection_fields",
    "verify_search_projection",
]
