"""Digest-bound robots.txt evaluation for anonymous image discovery."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from core.schema import assert_valid

ROBOTS_EVIDENCE_INVALID = "DATA.SOURCE.ROBOTS_EVIDENCE_INVALID"
ROBOTS_ACCESS_BLOCKED = "DATA.SOURCE.ROBOTS_ACCESS_BLOCKED"
_HOSTS = {
    "pinterest": ("pinterest.com",),
    "tuchong": ("tuchong.com",),
}
_MAX_BODY_BYTES = 1024 * 1024


class ProfessionalImageRobotsEvidenceError(ValueError):
    """Typed robots evidence or access blocker."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> None:
    raise ProfessionalImageRobotsEvidenceError(code, message)


def _digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _https(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    parsed = urlsplit(text)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        _fail(ROBOTS_EVIDENCE_INVALID, f"{label} must be anonymous HTTPS")
    return text


def _host_allowed(provider: str, host: str) -> bool:
    return any(host == root or host.endswith("." + root) for root in _HOSTS[provider])


def _evaluate(*, robots_body: str, user_agent: str, target_url: str) -> bool:
    parser = RobotFileParser()
    parser.set_url(target_url)
    parser.parse(robots_body.splitlines())
    return bool(parser.can_fetch(user_agent, target_url))


def build_professional_image_robots_evidence(
    *,
    provider: str,
    robots_url: str,
    robots_body: str,
    user_agent: str,
    target_url: str,
    observed_at: str,
) -> dict[str, Any]:
    """Evaluate supplied robots bytes; callers cannot provide the decision."""
    normalized_provider = str(provider or "").strip().casefold()
    if normalized_provider not in _HOSTS:
        _fail(ROBOTS_EVIDENCE_INVALID, f"unsupported provider: {provider}")
    robots = _https(robots_url, label="robotsUrl")
    target = _https(target_url, label="targetUrl")
    robots_parsed, target_parsed = urlsplit(robots), urlsplit(target)
    if robots_parsed.path != "/robots.txt" or robots_parsed.query:
        _fail(ROBOTS_EVIDENCE_INVALID, "robotsUrl must be the provider /robots.txt")
    if not _host_allowed(normalized_provider, str(robots_parsed.hostname or "")):
        _fail(ROBOTS_EVIDENCE_INVALID, "robotsUrl provider host mismatch")
    if not _host_allowed(normalized_provider, str(target_parsed.hostname or "")):
        _fail(ROBOTS_EVIDENCE_INVALID, "targetUrl provider host mismatch")
    body = str(robots_body or "")
    if not body.strip() or len(body.encode("utf-8")) > _MAX_BODY_BYTES:
        _fail(ROBOTS_EVIDENCE_INVALID, "robotsBody is missing or oversized")
    agent = str(user_agent or "").strip()
    observed = str(observed_at or "").strip()
    if not agent or not observed:
        _fail(ROBOTS_EVIDENCE_INVALID, "userAgent and observedAt are required")
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.professional_image_robots_evidence",
        "provider": normalized_provider,
        "robotsUrl": robots,
        "robotsBody": body,
        "robotsBodySha256": "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "userAgent": agent,
        "targetUrl": target,
        "observedAt": observed,
        "allowed": _evaluate(robots_body=body, user_agent=agent, target_url=target),
    }
    document = {**stable, "evidenceDigest": _digest(stable)}
    assert_valid(
        document,
        "source",
        "professional_image_robots_evidence",
        label="professional image robots evidence",
    )
    return document


def validate_professional_image_robots_evidence(
    evidence: Mapping[str, Any], *, provider: str, target_url: str
) -> dict[str, Any]:
    """Recompute the body, evaluation and document digests for one request."""
    try:
        assert_valid(
            dict(evidence),
            "source",
            "professional_image_robots_evidence",
            label="professional image robots evidence",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        _fail(ROBOTS_EVIDENCE_INVALID, str(exc))
    stable = {key: value for key, value in evidence.items() if key != "evidenceDigest"}
    rebuilt = build_professional_image_robots_evidence(
        provider=str(evidence["provider"]),
        robots_url=str(evidence["robotsUrl"]),
        robots_body=str(evidence["robotsBody"]),
        user_agent=str(evidence["userAgent"]),
        target_url=str(evidence["targetUrl"]),
        observed_at=str(evidence["observedAt"]),
    )
    if evidence.get("evidenceDigest") != _digest(stable) or dict(evidence) != rebuilt:
        _fail(ROBOTS_EVIDENCE_INVALID, "robots evidence digest or evaluation drift")
    if str(evidence["provider"]) != str(provider).strip().casefold():
        _fail(ROBOTS_EVIDENCE_INVALID, "robots evidence provider drift")
    if str(evidence["targetUrl"]) != str(target_url).strip():
        _fail(ROBOTS_EVIDENCE_INVALID, "robots evidence targetUrl drift")
    if evidence.get("allowed") is not True:
        _fail(ROBOTS_ACCESS_BLOCKED, "robots policy disallows anonymous target access")
    return rebuilt


__all__ = [
    "ROBOTS_ACCESS_BLOCKED",
    "ROBOTS_EVIDENCE_INVALID",
    "ProfessionalImageRobotsEvidenceError",
    "build_professional_image_robots_evidence",
    "validate_professional_image_robots_evidence",
]
