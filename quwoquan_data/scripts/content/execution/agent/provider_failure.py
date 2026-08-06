"""Stable semantic-provider failure classification.

Provider SDKs expose different exception classes and free-form messages.  This
module admits those values once and returns the closed failure class plus a
stable provider-specific error code.  It never chooses another provider.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.control_types import AgentFailureKind


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    kind: AgentFailureKind
    error_code: str
    retryable: bool
    retry_after_seconds: int = 0


def _retry_after_seconds(text: str) -> int:
    lowered = str(text or "").casefold()
    for pattern in (
        r"retry[- ]after\s*[:=]?\s*(\d+)\s*(?:s|sec|second|seconds)?",
        r"try again in\s+(\d+)\s*(?:s|sec|second|seconds)",
    ):
        match = re.search(pattern, lowered)
        if match:
            return max(0, int(match.group(1)))
    return 0


def classify_provider_failure(
    message: str,
    *,
    code: str = "",
    status: int | None = None,
    explicit_retryable: bool = False,
) -> ProviderFailure:
    text = " ".join(str(message or "").split())
    lowered = text.casefold()
    normalized_code = str(code or "").strip().casefold()
    retry_after = _retry_after_seconds(text)

    if status in {401, 403} or normalized_code in {
        "authentication_failed",
        "invalid_api_key",
        "unauthorized",
    } or any(
        marker in lowered
        for marker in (
            "not logged in",
            "authentication required",
            "unauthorized",
            "invalid api key",
            "access token expired",
        )
    ):
        return ProviderFailure(
            AgentFailureKind.AUTHENTICATION_REJECTED,
            "semantic_provider_authentication_rejected",
            False,
        )

    if normalized_code in {
        "billing_limit_reached",
        "insufficient_credits",
        "quota_exceeded",
        "usage_limit",
    } or any(
        marker in lowered
        for marker in (
            "you've hit your usage limit",
            "usage limit",
            "spend limit",
            "monthly cycle ends",
            "insufficient credits",
            "quota exceeded",
        )
    ):
        return ProviderFailure(
            AgentFailureKind.PROVIDER_REJECTED,
            "semantic_provider_quota_exhausted",
            False,
        )

    if status == 429 or normalized_code in {
        "rate_limit",
        "rate_limited",
        "too_many_requests",
    } or any(
        marker in lowered
        for marker in ("rate limit", "rate-limit", "too many requests", "http 429")
    ):
        return ProviderFailure(
            AgentFailureKind.PROVIDER_REJECTED,
            "semantic_provider_rate_limited",
            True,
            retry_after,
        )

    if normalized_code in {"capacity", "overloaded", "provider_busy"} or any(
        marker in lowered
        for marker in (
            "capacity unavailable",
            "provider capacity",
            "provider overloaded",
            "service overloaded",
        )
    ):
        return ProviderFailure(
            AgentFailureKind.PROVIDER_REJECTED,
            "semantic_provider_capacity_unavailable",
            True,
            retry_after,
        )

    if any(
        marker in lowered
        for marker in (
            "name or service not known",
            "nodename nor servname provided",
            "temporary failure in name resolution",
            "dns",
            "could not resolve host",
        )
    ):
        return ProviderFailure(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            "semantic_provider_dns_unavailable",
            True,
            retry_after,
        )

    if any(marker in lowered for marker in ("timed out", "timeout")):
        return ProviderFailure(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            "semantic_provider_transport_timeout",
            True,
            retry_after,
        )

    if explicit_retryable or status in {502, 503, 504} or any(
        marker in lowered
        for marker in (
            "connection reset",
            "connection refused",
            "temporarily unavailable",
            "network",
            "tls",
            "http 502",
            "http 503",
            "http 504",
        )
    ):
        return ProviderFailure(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            "semantic_provider_transport_unavailable",
            True,
            retry_after,
        )

    return ProviderFailure(
        AgentFailureKind.SDK_EXECUTION_FAILED,
        normalized_code or "semantic_provider_execution_failed",
        False,
        retry_after,
    )


__all__ = ["ProviderFailure", "classify_provider_failure"]
