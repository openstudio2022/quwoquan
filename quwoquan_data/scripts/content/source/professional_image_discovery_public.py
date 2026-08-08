"""Parse anonymous Pinterest/Tuchong responses into an immutable candidate catalog.

This module only consumes response bytes already obtained through an anonymous,
public request.  It does not perform network I/O, accept cookies/credentials, or
turn transformed thumbnails into original-asset candidates.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from content.source.professional_image_discovery_public_parser import (
    RawPublicImageCandidate,
    extract_public_image_candidates,
)
from content.source.professional_image_robots_evidence import (
    ProfessionalImageRobotsEvidenceError,
    validate_professional_image_robots_evidence,
)
from core.schema import assert_valid


PROVIDERS = ("pinterest", "tuchong")
CATALOG_REVISION = "public-professional-image-candidates-v1"
DISCOVERY_INVALID = "DATA.SOURCE.PUBLIC_DISCOVERY_INVALID"
DISCOVERY_RESTRICTED = "DATA.SOURCE.PUBLIC_DISCOVERY_RESTRICTED"
SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"

_DISPLAY_NAMES = {"pinterest": "Pinterest", "tuchong": "图虫"}
_PROVIDER_HOSTS = {
    "pinterest": ("pinterest.com",),
    "tuchong": ("tuchong.com",),
}
_ASSET_HOSTS = {
    "pinterest": ("pinimg.com",),
    "tuchong": ("tuchong.com",),
}
_RESTRICTED_MARKERS = (
    "cf-chl-",
    "g-recaptcha",
    "captcha challenge",
    "login required",
    "登录后查看",
    "请完成安全验证",
    "paywall required",
)
_THUMBNAIL_PATH = re.compile(
    r"(?:^|/)(?:thumb(?:nail)?s?|small|medium|236x|474x|564x|75x75)(?:/|$)",
    re.IGNORECASE,
)
_MAX_RESPONSE_CHARACTERS = 16 * 1024 * 1024


class ProfessionalImagePublicDiscoveryError(RuntimeError):
    """Typed rejection for inaccessible or untrustworthy public discovery."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _error(code: str, message: str) -> ProfessionalImagePublicDiscoveryError:
    return ProfessionalImagePublicDiscoveryError(code, message)


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _timestamp(value: object) -> str:
    text = _clean_text(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error(DISCOVERY_INVALID, "observedAt must be a date-time") from exc
    if parsed.tzinfo is None:
        raise _error(DISCOVERY_INVALID, "observedAt must be a timezone-aware date-time")
    return text


def _host_matches(host: str, roots: tuple[str, ...]) -> bool:
    return any(host == root or host.endswith("." + root) for root in roots)


def _https_url(value: object, *, label: str) -> str:
    text = _clean_text(value)
    parsed = urlsplit(text)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise _error(DISCOVERY_INVALID, f"{label} must be anonymous HTTPS")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path or "/", query, ""))


def _owned_url(value: object, *, provider: str, asset: bool, label: str) -> str:
    url = _https_url(value, label=label)
    host = str(urlsplit(url).hostname or "").lower()
    roots = _ASSET_HOSTS[provider] if asset else _PROVIDER_HOSTS[provider]
    if not _host_matches(host, roots):
        raise _error(DISCOVERY_INVALID, f"{label} host does not belong to {provider}")
    return url


def _validate_plan(
    plan: Mapping[str, Any],
) -> tuple[dict[str, int], dict[str, set[str]]]:
    try:
        assert_valid(
            dict(plan),
            "source",
            "professional_image_discovery_plan",
            label="professional image discovery plan",
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _error(DISCOVERY_INVALID, f"discovery plan is invalid: {exc}") from exc
    stable = {
        key: plan[key]
        for key in (
            "catalogRef",
            "catalogDigest",
            "dimensions",
            "candidateCount",
            "providerCandidateCounts",
            "candidates",
        )
    }
    if plan.get("planDigest") != _digest(stable):
        raise _error(DISCOVERY_INVALID, "discovery plan digest drift")
    rows = plan.get("providerCandidateCounts")
    if not isinstance(rows, list) or [row.get("provider") for row in rows[:2]] != list(
        PROVIDERS
    ):
        raise _error(
            DISCOVERY_INVALID,
            "discovery plan must keep Pinterest first and Tuchong second",
        )
    result: dict[str, int] = {}
    for row in rows[:2]:
        provider = str(row.get("provider") or "")
        count = row.get("plannedAssetCount")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise _error(DISCOVERY_INVALID, f"{provider} planned count is invalid")
        result[provider] = count
    allowed_pages = {provider: set() for provider in PROVIDERS}
    for candidate in plan["candidates"]:
        provider = str(candidate["provider"])
        if provider in allowed_pages:
            allowed_pages[provider].add(
                _owned_url(
                    candidate["discoveryUrl"],
                    provider=provider,
                    asset=False,
                    label=f"{provider}.plannedDiscoveryUrl",
                )
            )
    if any(not values for values in allowed_pages.values()):
        raise _error(DISCOVERY_INVALID, "discovery plan provider URLs are incomplete")
    return result, allowed_pages


def _validate_response(
    response: Mapping[str, Any], *, allowed_pages: Mapping[str, set[str]]
) -> tuple[str, str, str, str, str]:
    provider = _clean_text(response.get("provider")).lower()
    if provider not in PROVIDERS:
        raise _error(DISCOVERY_INVALID, f"unsupported public image provider: {provider}")
    source_page_url = _owned_url(
        response.get("sourcePageUrl"),
        provider=provider,
        asset=False,
        label=f"{provider}.sourcePageUrl",
    )
    if source_page_url not in allowed_pages[provider]:
        raise _error(
            DISCOVERY_INVALID,
            f"{provider} response is not bound to a frozen discovery candidate",
        )
    status = response.get("statusCode")
    if isinstance(status, bool) or not isinstance(status, int):
        raise _error(DISCOVERY_INVALID, f"{provider} statusCode is invalid")
    if status in {401, 403, 407, 429}:
        raise _error(DISCOVERY_RESTRICTED, f"{provider} response is access controlled")
    if status < 200 or status >= 300:
        raise _error(DISCOVERY_INVALID, f"{provider} response status is {status}")
    content_type = _clean_text(response.get("contentType")).lower().split(";", 1)[0]
    if content_type not in {"text/html", "application/json"}:
        raise _error(DISCOVERY_INVALID, f"{provider} contentType is unsupported")
    body = response.get("body")
    if not isinstance(body, str) or not body.strip():
        raise _error(DISCOVERY_INVALID, f"{provider} response body is missing")
    if len(body) > _MAX_RESPONSE_CHARACTERS:
        raise _error(DISCOVERY_INVALID, f"{provider} response body exceeds safety limit")
    access = response.get("accessEvidence")
    if not isinstance(access, Mapping):
        raise _error(DISCOVERY_RESTRICTED, f"{provider} anonymous access evidence is missing")
    expected = {
        "anonymousRequest": True,
        "cookiesSent": False,
        "credentialsSent": False,
        "loginRequired": False,
        "captchaRequired": False,
        "paywallRequired": False,
        "technicalRestrictionDetected": False,
    }
    if "robotsAllowed" in access or any(
        access.get(key) is not value for key, value in expected.items()
    ):
        raise _error(
            DISCOVERY_RESTRICTED,
            f"{provider} response was not obtained through an allowed anonymous request",
        )
    robots_evidence = response.get("robotsEvidence")
    if not isinstance(robots_evidence, Mapping):
        raise _error(DISCOVERY_RESTRICTED, f"{provider} robots evidence is missing")
    try:
        verified_robots = validate_professional_image_robots_evidence(
            robots_evidence,
            provider=provider,
            target_url=source_page_url,
        )
    except ProfessionalImageRobotsEvidenceError as exc:
        raise _error(DISCOVERY_RESTRICTED, str(exc)) from exc
    request_headers = response.get("requestHeaders") or {}
    if not isinstance(request_headers, Mapping):
        raise _error(DISCOVERY_RESTRICTED, f"{provider} request headers are invalid")
    if {str(key).lower() for key in request_headers} & {"cookie", "authorization"}:
        raise _error(DISCOVERY_RESTRICTED, f"{provider} request carried credentials")
    lowered = body.lower()
    if any(marker in lowered for marker in _RESTRICTED_MARKERS):
        raise _error(DISCOVERY_RESTRICTED, f"{provider} returned a challenge page")
    return (
        provider,
        source_page_url,
        content_type,
        body,
        str(verified_robots["evidenceDigest"]),
    )


def _candidate_issue(row: RawPublicImageCandidate) -> tuple[str, str]:
    if not row.creator:
        return "DATA.SOURCE.CREATOR_MISSING", "creator is missing"
    if not row.title:
        return "DATA.SOURCE.TITLE_MISSING", "title is missing"
    try:
        asset_url = _owned_url(
            row.asset_url,
            provider=row.provider,
            asset=True,
            label="candidate assetUrl",
        )
    except ProfessionalImagePublicDiscoveryError as exc:
        return "DATA.SOURCE.NON_HTTPS_OR_FOREIGN_ASSET", str(exc)
    parsed = urlsplit(asset_url)
    query_keys = {key.lower() for key, _value in parse_qsl(parsed.query)}
    transformed = bool(query_keys & {"w", "width", "h", "height", "resize", "imageview2"})
    pinterest_not_original = row.provider == "pinterest" and "/originals/" not in parsed.path.lower()
    if (
        not row.original_signal
        or transformed
        or pinterest_not_original
        or _THUMBNAIL_PATH.search(parsed.path)
    ):
        return "DATA.SOURCE.THUMBNAIL_NOT_ORIGINAL", "asset is not an original candidate"
    return "", ""


def _response_projection(response: Mapping[str, Any]) -> dict[str, Any]:
    access = response.get("accessEvidence")
    return {
        "provider": response.get("provider"),
        "sourcePageUrl": response.get("sourcePageUrl"),
        "statusCode": response.get("statusCode"),
        "contentType": response.get("contentType"),
        "accessEvidence": dict(access) if isinstance(access, Mapping) else access,
        "requestHeaderNames": sorted(
            str(key).lower()
            for key in (response.get("requestHeaders") or {})
        ),
        "bodyDigest": _digest(response.get("body")),
        "robotsEvidenceDigest": (response.get("robotsEvidence") or {}).get(
            "evidenceDigest"
        ),
    }


def _catalog_core(catalog: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: catalog[key]
        for key in (
            "catalogRevision",
            "discoveryPlanId",
            "discoveryPlanDigest",
            "observedAt",
            "sourceResponses",
            "providerCounts",
            "candidateCount",
            "rejectedAssetCount",
            "candidates",
            "rejections",
        )
    }


def build_professional_image_public_candidate_catalog(
    *,
    discovery_plan: Mapping[str, Any],
    responses: Iterable[Mapping[str, Any]],
    observed_at: str,
) -> dict[str, Any]:
    """Build one digest-bound catalog from anonymous HTML/API responses."""

    planned, allowed_pages = _validate_plan(discovery_plan)
    observed = _timestamp(observed_at)
    validated: list[tuple[str, str, str, str, str, Mapping[str, Any]]] = []
    for response in responses:
        if not isinstance(response, Mapping):
            raise _error(DISCOVERY_INVALID, "public discovery response must be an object")
        provider, page, content_type, body, robots_digest = _validate_response(
            response, allowed_pages=allowed_pages
        )
        validated.append(
            (provider, page, content_type, body, robots_digest, response)
        )
    response_counts = Counter(row[0] for row in validated)
    if set(response_counts) != set(PROVIDERS):
        raise _error(DISCOVERY_INVALID, "Pinterest and Tuchong responses are both required")

    discovered = Counter()
    accepted = Counter()
    rejected = Counter()
    duplicates = Counter()
    source_responses: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    for provider in PROVIDERS:
        for current, page, content_type, body, robots_digest, raw_response in validated:
            if current != provider:
                continue
            response_digest = _digest(_response_projection(raw_response))
            source_responses.append(
                {
                    "provider": provider,
                    "sourcePageUrl": page,
                    "contentType": content_type,
                    "robotsEvidenceDigest": robots_digest,
                    "responseDigest": response_digest,
                }
            )
            try:
                raw_candidates = extract_public_image_candidates(
                    provider=provider,
                    content_type=content_type,
                    body=body,
                    source_page_url=page,
                )
            except ValueError as exc:
                raise _error(DISCOVERY_INVALID, str(exc)) from exc
            for raw_candidate in raw_candidates:
                discovered[provider] += 1
                issue_code, issue = _candidate_issue(raw_candidate)
                asset_key = ""
                if not issue_code:
                    asset_key = _owned_url(
                        raw_candidate.asset_url,
                        provider=provider,
                        asset=True,
                        label="candidate assetUrl",
                    )
                    if asset_key in seen_assets:
                        issue_code = "DATA.SOURCE.DUPLICATE_CANDIDATE"
                        issue = "assetUrl already exists in this catalog"
                        duplicates[provider] += 1
                if issue_code:
                    rejected[provider] += 1
                    rejections.append(
                        {
                            "provider": provider,
                            "sourcePageUrl": raw_candidate.source_page_url,
                            "candidateAssetUrl": raw_candidate.asset_url,
                            "reasonCode": issue_code,
                            "reason": issue,
                            "responseDigest": response_digest,
                        }
                    )
                    continue
                seen_assets.add(asset_key)
                accepted[provider] += 1
                stable_candidate = {
                    "provider": provider,
                    "sourcePageUrl": raw_candidate.source_page_url,
                    "assetUrl": asset_key,
                    "creator": raw_candidate.creator,
                    "title": raw_candidate.title,
                    "observedAt": observed,
                    "originalAssetCandidate": True,
                    "responseDigest": response_digest,
                }
                candidates.append(
                    {
                        "candidateId": (
                            f"{provider}:public:{_digest(stable_candidate)[7:23]}"
                        ),
                        **stable_candidate,
                    }
                )
    shortfall = [provider for provider in PROVIDERS if accepted[provider] < 1]
    if shortfall:
        reasons = Counter(
            row["reasonCode"] for row in rejections if row["provider"] in shortfall
        )
        raise _error(
            SOURCE_POOL_SHORTFALL,
            f"no accepted original candidate for {','.join(shortfall)}; rejections={dict(reasons)}",
        )
    provider_counts = [
        {
            "provider": provider,
            "displayName": _DISPLAY_NAMES[provider],
            "priority": PROVIDERS.index(provider),
            "plannedAssetCount": planned[provider],
            "responseCount": response_counts[provider],
            "discoveredAssetCount": discovered[provider],
            "acceptedAssetCount": accepted[provider],
            "rejectedAssetCount": rejected[provider],
            "duplicateAssetCount": duplicates[provider],
        }
        for provider in PROVIDERS
    ]
    core: dict[str, Any] = {
        "catalogRevision": CATALOG_REVISION,
        "discoveryPlanId": discovery_plan["planId"],
        "discoveryPlanDigest": discovery_plan["planDigest"],
        "observedAt": observed,
        "sourceResponses": source_responses,
        "providerCounts": provider_counts,
        "candidateCount": len(candidates),
        "rejectedAssetCount": len(rejections),
        "candidates": candidates,
        "rejections": rejections,
    }
    catalog_digest = _digest(core)
    document = {
        "schema": "quwoquan_data.professional_image_public_candidate_catalog",
        "catalogId": f"professional-image-public-{catalog_digest[7:23]}",
        "catalogDigest": catalog_digest,
        **core,
    }
    assert_valid(
        document,
        "source",
        "professional_image_public_candidate_catalog",
        label="professional image public candidate catalog",
    )
    return document


def write_professional_image_public_candidate_catalog(
    catalog: Mapping[str, Any], *, output_root: Path
) -> Path:
    """Write one caller-scoped, create-once catalog; no canonical default exists."""

    payload = dict(catalog)
    assert_valid(
        payload,
        "source",
        "professional_image_public_candidate_catalog",
        label="professional image public candidate catalog",
    )
    if payload.get("catalogDigest") != _digest(_catalog_core(payload)):
        raise _error(DISCOVERY_INVALID, "public candidate catalog digest drift")
    destination = output_root.expanduser().resolve() / f"{payload['catalogId']}.json"
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if destination.read_bytes() != body:
            raise _error(DISCOVERY_INVALID, f"public candidate catalog collision: {destination}")
        return destination
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return destination


__all__ = [
    "CATALOG_REVISION",
    "DISCOVERY_INVALID",
    "DISCOVERY_RESTRICTED",
    "SOURCE_POOL_SHORTFALL",
    "ProfessionalImagePublicDiscoveryError",
    "build_professional_image_public_candidate_catalog",
    "write_professional_image_public_candidate_catalog",
]
