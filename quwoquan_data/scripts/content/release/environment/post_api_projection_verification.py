"""Verify release-owned feed and search public projections."""
from __future__ import annotations

import time
from collections.abc import Mapping
from http import HTTPStatus
from pathlib import Path
from typing import Any

from content.release.environment.post_api_media_verification import (
    PostApiCase,
    PostApiVerificationError,
    _object,
)
from content.release.environment.post_api_release_cases import CreatorProfileCase
from content.release.environment.post_api_search_contract import (
    _CANONICAL_ERROR_CODE,
    SEARCH_PAGE_ID,
    _content_post_projection_fields,
    _search_content_type,
    _search_retry_policy,
    _SearchRetryableError,
    _SearchRetryPolicy,
)
from content.release.environment.public_api_client import (
    PublicApiClient,
    PublicApiClientError,
    PublicApiRequestIdentity,
)
from core.io import read_json


def _monotonic_seconds() -> float:
    return time.monotonic()


def _sleep_seconds(seconds: float) -> None:
    time.sleep(seconds)


class SearchProjectionVerificationError(PostApiVerificationError):
    """Search readiness blocker retaining bounded physical-attempt evidence."""

    def __init__(self, message: str, *, operation_attempts: list[dict[str, Any]]):
        super().__init__(message)
        self.operation_attempts = tuple(dict(row) for row in operation_attempts)


def _operation_payload(response: Any, *, endpoint: str) -> dict[str, Any]:
    operation = getattr(response, "operation", None)
    if operation is None:
        raise PostApiVerificationError(f"{endpoint} lacks request trace evidence")
    return operation.as_payload()


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


def _safe_evidence_value(value: object, *, default: str = "none") -> str:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 128:
        return default
    if not all(character.isalnum() or character in "._:-" for character in candidate):
        return default
    return candidate


def _canonical_error_code(response: Any) -> str:
    payload = getattr(response, "payload", {})
    raw_code = payload.get("code") if isinstance(payload, Mapping) else None
    candidate = _safe_evidence_value(raw_code)
    if _CANONICAL_ERROR_CODE.fullmatch(candidate) is None:
        return "none"
    return candidate


def _recovery_action(response: Any) -> str:
    payload = getattr(response, "payload", {})
    recovery = payload.get("recovery") if isinstance(payload, Mapping) else None
    action = (
        str(recovery.get("action") or "").strip()
        if isinstance(recovery, Mapping)
        else ""
    )
    if action not in {
        "retry",
        "surface",
        "absorb",
        "fallback",
        "escalate",
        "compensate",
    }:
        return "none"
    return action


def _recovery_after_seconds(response: Any) -> int:
    payload = getattr(response, "payload", {})
    recovery = payload.get("recovery") if isinstance(payload, Mapping) else None
    if not isinstance(recovery, Mapping) or "afterSeconds" not in recovery:
        return 0
    value = recovery.get("afterSeconds")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return -1
    return value


def _retry_after_seconds(response: Any) -> int:
    headers = getattr(response, "headers", {})
    if not isinstance(headers, Mapping):
        return -1
    raw_value = next(
        (
            value
            for key, value in headers.items()
            if str(key).strip().lower() == "retry-after"
        ),
        None,
    )
    if raw_value is None:
        return 0
    candidate = str(raw_value).strip()
    if not candidate.isascii() or not candidate.isdecimal():
        return -1
    value = int(candidate)
    return value if value <= 86400 else -1


def _search_attempt_payload(
    response: Any,
    *,
    attempt: int,
    request_identity: PublicApiRequestIdentity,
) -> dict[str, Any]:
    operation = _operation_payload(response, endpoint="search")
    if (
        operation["requestId"] != request_identity.request_id
        or operation["traceId"] != request_identity.trace_id
    ):
        raise PostApiVerificationError(
            "search operation evidence drifted from its logical request identity"
        )
    return {
        "attempt": attempt,
        "canonicalErrorCode": _canonical_error_code(response),
        "recoveryAction": _recovery_action(response),
        "recoveryAfterSeconds": max(0, _recovery_after_seconds(response)),
        "retryAfterSeconds": max(0, _retry_after_seconds(response)),
        "operation": operation,
    }


def _search_retry_directive(
    response: Any,
    *,
    policy: _SearchRetryPolicy,
) -> _SearchRetryableError | None:
    status = int(getattr(response, "status", 0) or 0)
    code = _canonical_error_code(response)
    after_seconds = _recovery_after_seconds(response)
    retry_after_seconds = _retry_after_seconds(response)
    if (
        _recovery_action(response) != "retry"
        or after_seconds < 0
        or retry_after_seconds < 0
        or retry_after_seconds != after_seconds
    ):
        return None
    return next(
        (
            row
            for row in policy.retryable_errors
            if row.code == code
            and row.http_status == status
            and row.recovery_after_seconds == after_seconds
        ),
        None,
    )


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
    canonical_error_code = _canonical_error_code(response)
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


def _search_deadline_failure_message(
    response: Any,
    *,
    query: str,
    object_types: list[str],
) -> str:
    operation = getattr(response, "operation", None)
    if operation is None:
        raise PostApiVerificationError("search lacks request trace evidence")
    target_types = ",".join(
        _safe_evidence_value(value, default="invalid") for value in object_types
    )
    return (
        "Search verification failed: "
        "outcome=deadline_exhausted "
        f"status={int(getattr(response, 'status', 0) or 0)} "
        f"canonicalErrorCode={_canonical_error_code(response)} "
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
    content_types: list[str] | None = None,
    object_id: str,
) -> dict[str, Any]:
    request_body: dict[str, Any] = {
        "query": query,
        "mode": "result",
        "objectTypes": object_types,
        "ids": [object_id],
        "limit": 20,
    }
    if content_types:
        request_body["contentTypes"] = content_types
    policy = _search_retry_policy()
    attempt_limit = (
        policy.max_attempts if policy.retry_mode == "idempotent" else 1
    )
    deadline = _monotonic_seconds() + (
        policy.total_timeout_ms(attempt_limit=attempt_limit) / 1000
    )
    request_identity = client.new_request_identity(page_id=SEARCH_PAGE_ID)
    attempts: list[dict[str, Any]] = []
    first_failure_message = ""
    for attempt in range(1, attempt_limit + 1):
        remaining_seconds = deadline - _monotonic_seconds()
        if remaining_seconds <= 0:
            raise SearchProjectionVerificationError(
                first_failure_message or "Search verification deadline exhausted",
                operation_attempts=attempts,
            )
        try:
            response = client.post_json(
                "search",
                page_id=SEARCH_PAGE_ID,
                body=request_body,
                session_header_name="X-Session-Id",
                request_identity=request_identity,
                timeout_seconds=min(
                    policy.timeout_ms / 1000,
                    remaining_seconds,
                ),
            )
            response_received_at = _monotonic_seconds()
            attempts.append(
                _search_attempt_payload(
                    response,
                    attempt=attempt,
                    request_identity=request_identity,
                )
            )
        except (PublicApiClientError, PostApiVerificationError) as exc:
            if first_failure_message:
                raise SearchProjectionVerificationError(
                    first_failure_message,
                    operation_attempts=attempts,
                ) from exc
            raise
        if response_received_at >= deadline:
            if not first_failure_message:
                first_failure_message = _search_deadline_failure_message(
                    response,
                    query=query,
                    object_types=object_types,
                )
            raise SearchProjectionVerificationError(
                first_failure_message,
                operation_attempts=attempts,
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
        if response.status == HTTPStatus.OK and object_id in matched:
            return {
                "query": query,
                "status": response.status,
                "matchedObjectIds": matched,
                "attempts": attempts,
            }
        failure_message = _search_failure_message(
            response,
            query=query,
            object_types=object_types,
        )
        if not first_failure_message:
            first_failure_message = failure_message
        retry_directive = _search_retry_directive(response, policy=policy)
        if attempt >= attempt_limit or retry_directive is None:
            raise SearchProjectionVerificationError(
                first_failure_message,
                operation_attempts=attempts,
            )
        retry_after_seconds = retry_directive.recovery_after_seconds
        if _monotonic_seconds() + retry_after_seconds >= deadline:
            raise SearchProjectionVerificationError(
                first_failure_message,
                operation_attempts=attempts,
            )
        if retry_after_seconds:
            _sleep_seconds(retry_after_seconds)
    raise SearchProjectionVerificationError(
        first_failure_message,
        operation_attempts=attempts,
    )


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
            object_types=["content.post"],
            content_types=[_search_content_type(case.content_type.value)],
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
            object_types=["user.profile"],
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
