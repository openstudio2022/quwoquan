"""Canonical contract inputs backing release-owned search verification.

Everything here is decoded from the frozen service contracts. The retry
boundary, the public projection field set and the searchable content types are
read, never assumed, so a probe can never be more permissive than the contract
it claims to verify.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

import yaml
from content.release.environment.post_api_media_verification import (
    PostApiVerificationError,
)
from core.paths import REPO_ROOT

CONTENT_POST_PROJECTION_PATH = REPO_ROOT / (
    "quwoquan_service/services/content-service/contracts/content/post/projections/"
    "content_post_projection.yaml"
)
SEARCH_OPERATIONS_PATH = REPO_ROOT / (
    "quwoquan_service/services/search-service/contracts/search/"
    "search_index_view/operations.yaml"
)
SEARCH_ERRORS_PATH = SEARCH_OPERATIONS_PATH.with_name("errors.yaml")
GATEWAY_ERRORS_PATH = REPO_ROOT / (
    "quwoquan_service/services/api-edge/contracts/edge_security/"
    "rate_limit_bucket/errors.yaml"
)
SEARCH_PAGE_ID = "search.global"
_SEARCH_CONTENT_TYPES = frozenset({"article", "image", "video"})
_CANONICAL_ERROR_CODE = re.compile(
    r"[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z][a-z0-9_]*"
)


@dataclass(frozen=True)
class _SearchRetryableError:
    code: str
    http_status: int
    recovery_after_seconds: int


@dataclass(frozen=True)
class _SearchRetryPolicy:
    retry_mode: str
    max_attempts: int
    timeout_ms: int
    retryable_errors: tuple[_SearchRetryableError, ...]

    def total_timeout_ms(self, *, attempt_limit: int) -> int:
        """Bound attempts and every contract-directed wait under one deadline."""

        maximum_wait_seconds = max(
            (row.recovery_after_seconds for row in self.retryable_errors),
            default=0,
        )
        return (
            self.timeout_ms * attempt_limit
            + maximum_wait_seconds * 1000 * max(0, attempt_limit - 1)
        )


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


@lru_cache(maxsize=1)
def _search_retry_policy() -> _SearchRetryPolicy:
    """Read the retry boundary from the canonical Search operation contract."""
    try:
        document = yaml.safe_load(SEARCH_OPERATIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PostApiVerificationError(
            f"canonical Search operations contract is unreadable: {SEARCH_OPERATIONS_PATH}"
        ) from exc
    if not isinstance(document, Mapping):
        raise PostApiVerificationError(
            "canonical Search operations contract must be an object"
        )
    routes = document.get("api_routes")
    if not isinstance(routes, list):
        raise PostApiVerificationError(
            "canonical Search operations contract lacks api_routes"
        )
    for route in routes:
        if not isinstance(route, Mapping):
            continue
        if (
            str(route.get("method") or "").upper() != "POST"
            or str(route.get("path") or "") != "/search"
            or str(route.get("operation") or "") != "Search"
        ):
            continue
        reliability = route.get("reliability")
        if not isinstance(reliability, Mapping):
            raise PostApiVerificationError(
                "canonical Search operation lacks reliability contract"
            )
        retry_mode = str(reliability.get("retry_mode") or "").strip()
        max_attempts = reliability.get("max_attempts")
        timeout_ms = reliability.get("timeout_ms")
        if retry_mode not in {"none", "idempotent"}:
            raise PostApiVerificationError(
                "canonical Search operation retry_mode is invalid"
            )
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts < 1
        ):
            raise PostApiVerificationError(
                "canonical Search operation max_attempts is invalid"
            )
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or timeout_ms < 1
        ):
            raise PostApiVerificationError(
                "canonical Search operation timeout_ms is invalid"
            )
        raw_error_codes = route.get("error_codes")
        if not isinstance(raw_error_codes, list) or not raw_error_codes:
            raise PostApiVerificationError(
                "canonical Search operation error_codes must be a non-empty array"
            )
        search_error_codes = frozenset(
            str(value or "").strip() for value in raw_error_codes
        )
        retryable_errors = _load_search_retryable_errors(
            search_error_codes=search_error_codes,
        )
        if not retryable_errors:
            raise PostApiVerificationError(
                "canonical Search readiness has no retryable typed errors"
            )
        return _SearchRetryPolicy(
            retry_mode=retry_mode,
            max_attempts=max_attempts,
            timeout_ms=timeout_ms,
            retryable_errors=retryable_errors,
        )
    raise PostApiVerificationError(
        "canonical POST /search Search operation is missing"
    )


def _load_search_retryable_errors(
    *,
    search_error_codes: frozenset[str],
) -> tuple[_SearchRetryableError, ...]:
    """Decode only Search and gateway-transport errors from canonical YAML."""

    rows: list[_SearchRetryableError] = []
    for path, source in (
        (SEARCH_ERRORS_PATH, "search"),
        (GATEWAY_ERRORS_PATH, "gateway"),
    ):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise PostApiVerificationError(
                f"canonical {source} errors contract is unreadable: {path}"
            ) from exc
        definitions = document.get("errors") if isinstance(document, Mapping) else None
        if not isinstance(definitions, list):
            raise PostApiVerificationError(
                f"canonical {source} errors contract lacks errors"
            )
        for definition in definitions:
            if not isinstance(definition, Mapping):
                continue
            code = str(definition.get("code") or "").strip()
            reason = str(definition.get("reason") or "").strip()
            if source == "search":
                selected = code in search_error_codes
            else:
                selected = reason in {"upstream_unavailable", "upstream_timeout"}
            if not selected or definition.get("recovery_action") != "retry":
                continue
            status = definition.get("http_status")
            after_seconds = definition.get("recovery_after_seconds", 0)
            if (
                _CANONICAL_ERROR_CODE.fullmatch(code) is None
                or isinstance(status, bool)
                or not isinstance(status, int)
                or status < 400
                or status > 599
                or isinstance(after_seconds, bool)
                or not isinstance(after_seconds, int)
                or after_seconds < 0
            ):
                raise PostApiVerificationError(
                    f"canonical retryable error {code or 'unknown'} is invalid"
                )
            rows.append(
                _SearchRetryableError(
                    code=code,
                    http_status=status,
                    recovery_after_seconds=after_seconds,
                )
            )
    return tuple(sorted(rows, key=lambda row: row.code))


def _search_content_type(content_type: str) -> str:
    if content_type not in _SEARCH_CONTENT_TYPES:
        raise PostApiVerificationError(
            f"unsupported Content search projection type: {content_type}"
        )
    return content_type
