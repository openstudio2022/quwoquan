"""Freeze manual/API professional-image candidates without public-response fiction."""
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

from core.schema import assert_valid

CATALOG_REVISION = "governed-professional-image-candidates-v1"
GOVERNED_DISCOVERY_INVALID = "DATA.SOURCE.GOVERNED_DISCOVERY_INVALID"
_PROVIDERS = ("pinterest", "tuchong", "wikimedia_commons", "openverse")
_DISPLAY_NAMES = {
    "pinterest": "Pinterest",
    "tuchong": "图虫",
    "wikimedia_commons": "Wikimedia Commons",
    "openverse": "Openverse",
}
_PROVIDER_HOSTS = {
    "pinterest": ("pinterest.com",),
    "tuchong": ("tuchong.com",),
    "wikimedia_commons": ("commons.wikimedia.org",),
    "openverse": ("openverse.org",),
}
_ASSET_HOSTS = {
    "pinterest": ("pinimg.com",),
    "tuchong": ("tuchong.com",),
    "wikimedia_commons": ("upload.wikimedia.org",),
    "openverse": (),
}
_API_HOSTS = {
    "pinterest": ("api.pinterest.com", "pinterest.com"),
    "tuchong": ("open.tuchong.com", "tuchong.com"),
    "wikimedia_commons": ("commons.wikimedia.org", "api.wikimedia.org"),
    "openverse": ("api.openverse.org",),
}
_THUMBNAIL_PATH = re.compile(
    r"(?:^|/)(?:thumb(?:nail)?s?|small|medium|236x|474x|564x|75x75)(?:/|$)",
    re.IGNORECASE,
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_SCHEMAS = {
    "manual_file": "quwoquan_data.professional_image_manual_file_evidence",
    "supported_api": "quwoquan_data.professional_image_supported_api_evidence",
}
_EVIDENCE_FIELDS = (
    "schema",
    "provider",
    "acquisitionPath",
    "discoveryCandidateId",
    "sourcePageUrl",
    "assetUrl",
    "manualFile",
    "apiEvidence",
    "creator",
    "title",
    "observedAt",
    "contentSha256",
    "originalAssetCandidate",
    "generated",
)


class ProfessionalImageGovernedDiscoveryError(ValueError):
    """Typed rejection for forged or drifting manual/API discovery evidence."""

    def __init__(self, message: str) -> None:
        self.code = GOVERNED_DISCOVERY_INVALID
        super().__init__(f"{self.code}: {message}")


def _fail(message: str) -> None:
    raise ProfessionalImageGovernedDiscoveryError(message)


def _digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _text(value: object, *, label: str) -> str:
    rendered = " ".join(str(value or "").split())
    if not rendered:
        _fail(f"{label} is required")
    return rendered


def _timestamp(value: object, *, label: str) -> str:
    rendered = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProfessionalImageGovernedDiscoveryError(
            f"{label} must be a date-time"
        ) from exc
    if parsed.tzinfo is None:
        _fail(f"{label} must include a timezone")
    return rendered


def _safe_file(root: Path, ref: object) -> tuple[Path, str]:
    relative = Path(str(ref or "").strip())
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail("evidenceRef must be a safe relative reference")
    current = root.resolve()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail("evidenceRef must not traverse a symlink")
    if not current.is_file():
        _fail(f"evidenceRef is missing: {relative.as_posix()}")
    return current, relative.as_posix()


def _host_matches(host: str, roots: tuple[str, ...]) -> bool:
    return any(host == root or host.endswith("." + root) for root in roots)


def _https_url(value: object, *, provider: str, asset: bool, label: str) -> str:
    rendered = _text(value, label=label)
    parsed = urlsplit(rendered)
    roots = _ASSET_HOSTS[provider] if asset else _PROVIDER_HOSTS[provider]
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (roots and not _host_matches(str(parsed.hostname).lower(), roots))
    ):
        _fail(f"{label} must be provider-owned HTTPS")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path or "/", query, ""))


def _api_evidence_url(value: object, *, provider: str) -> str:
    rendered = _text(value, label="apiEvidence")
    parsed = urlsplit(rendered)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or not _host_matches(str(parsed.hostname).lower(), _API_HOSTS[provider])
    ):
        _fail("apiEvidence must be an official provider API HTTPS URL")
    return rendered


def _manual_file(value: object) -> str:
    relative = Path(_text(value, label="manualFile"))
    if relative.is_absolute() or ".." in relative.parts:
        _fail("manualFile must be a safe relative reference")
    return relative.as_posix()


def _evidence_candidate(
    document: Mapping[str, Any], *, evidence_ref: str, evidence_digest: str,
    evidence_file_sha256: str,
) -> dict[str, Any]:
    unknown = set(document) - set(_EVIDENCE_FIELDS)
    missing = set(_EVIDENCE_FIELDS) - set(document)
    if unknown or missing:
        _fail(
            "manual/API evidence fields drift: "
            f"missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    provider = _text(document["provider"], label="provider").lower()
    if provider not in _PROVIDERS:
        _fail(f"unsupported professional image provider: {provider}")
    path = _text(document["acquisitionPath"], label="acquisitionPath")
    if path not in _EVIDENCE_SCHEMAS:
        _fail("manual/API catalog forbids public_direct acquisition")
    if document["schema"] != _EVIDENCE_SCHEMAS[path]:
        _fail("manual/API evidence schema does not match acquisitionPath")
    candidate_id = _text(document["discoveryCandidateId"], label="discoveryCandidateId")
    if not re.fullmatch(
        rf"{provider}:(?:[a-z0-9_-]+:)?[0-9a-f]{{16}}", candidate_id
    ):
        _fail("discoveryCandidateId is not provider scoped")
    source_page = _https_url(
        document["sourcePageUrl"], provider=provider, asset=False, label="sourcePageUrl"
    )
    creator = _text(document["creator"], label="creator")
    title = _text(document["title"], label="title")
    observed_at = _timestamp(document["observedAt"], label="observedAt")
    content_sha = str(document["contentSha256"])
    if not _SHA256.fullmatch(content_sha):
        _fail("contentSha256 must identify the original asset bytes")
    if document["originalAssetCandidate"] is not True:
        _fail("candidate is not verified as an original asset")
    if document["generated"] is not False:
        _fail("generated image candidates are forbidden")
    asset_url = str(document["assetUrl"] or "").strip()
    manual_file = str(document["manualFile"] or "").strip()
    api_evidence = str(document["apiEvidence"] or "").strip()
    if path == "manual_file":
        if asset_url or api_evidence:
            _fail("manual_file evidence forbids assetUrl/apiEvidence")
        manual_file = _manual_file(manual_file)
    else:
        if manual_file or not api_evidence:
            _fail("supported_api evidence requires apiEvidence and forbids manualFile")
        api_evidence = _api_evidence_url(api_evidence, provider=provider)
        asset_url = _https_url(
            asset_url, provider=provider, asset=True, label="assetUrl"
        )
        parsed = urlsplit(asset_url)
        query_keys = {key.lower() for key, _value in parse_qsl(parsed.query)}
        transformed = bool(query_keys & {"w", "width", "h", "height", "resize", "imageview2"})
        pinterest_non_original = (
            provider == "pinterest" and "/originals/" not in parsed.path.lower()
        )
        if transformed or pinterest_non_original or _THUMBNAIL_PATH.search(parsed.path):
            _fail("supported_api assetUrl is a thumbnail/transformation, not an original")
    return {
        "candidateId": candidate_id,
        "provider": provider,
        "acquisitionPath": path,
        "sourcePageUrl": source_page,
        "creator": creator,
        "title": title,
        "observedAt": observed_at,
        "originalAssetCandidate": True,
        "generated": False,
        "originalAssetIdentity": {
            "contentSha256": content_sha,
            "sourceUrl": source_page,
            "assetUrl": asset_url,
            "manualFile": manual_file,
            "apiEvidence": api_evidence,
        },
        "pathEvidence": {
            "kind": path,
            "ref": evidence_ref,
            "digest": evidence_digest,
            "fileSha256": evidence_file_sha256,
        },
    }


def _catalog_core(catalog: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: catalog[key]
        for key in (
            "catalogRevision",
            "discoveryPlanId",
            "discoveryPlanDigest",
            "createdAt",
            "providerCounts",
            "candidateCount",
            "candidates",
        )
    }


def build_professional_image_governed_candidate_catalog(
    *, discovery_plan_id: str, discovery_plan_digest: str, created_at: str,
    evidence_root: Path, evidence_refs: Iterable[str],
) -> dict[str, Any]:
    """Build a digest-bound catalog from explicit manual-file/API evidence files."""
    plan_id = _text(discovery_plan_id, label="discoveryPlanId")
    if not _SHA256.fullmatch(discovery_plan_digest):
        _fail("discoveryPlanDigest must be sha256")
    created = _timestamp(created_at, label="createdAt")
    root = evidence_root.expanduser().resolve()
    candidates: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for raw_ref in sorted(str(value).strip() for value in evidence_refs):
        path, ref = _safe_file(root, raw_ref)
        if ref in seen_refs:
            _fail(f"duplicate evidenceRef: {ref}")
        seen_refs.add(ref)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProfessionalImageGovernedDiscoveryError(
                f"manual/API evidence is not readable JSON: {ref}: {exc}"
            ) from exc
        if not isinstance(document, dict):
            _fail(f"manual/API evidence must be an object: {ref}")
        candidates.append(
            _evidence_candidate(
                document,
                evidence_ref=ref,
                evidence_digest=_digest(document),
                evidence_file_sha256=_file_sha256(path),
            )
        )
    if not candidates:
        _fail("at least one manual/API evidence file is required")
    candidate_ids = [row["candidateId"] for row in candidates]
    content_ids = [row["originalAssetIdentity"]["contentSha256"] for row in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        _fail("duplicate discoveryCandidateId in governed catalog")
    if len(content_ids) != len(set(content_ids)):
        _fail("duplicate original contentSha256 in governed catalog")
    candidates.sort(key=lambda row: (row["provider"], row["acquisitionPath"], row["candidateId"]))
    counts = Counter((row["provider"], row["acquisitionPath"]) for row in candidates)
    provider_counts = [
        {
            "provider": provider,
            "displayName": _DISPLAY_NAMES[provider],
            "acquisitionPath": path,
            "candidateCount": count,
        }
        for (provider, path), count in sorted(counts.items())
    ]
    core: dict[str, Any] = {
        "catalogRevision": CATALOG_REVISION,
        "discoveryPlanId": plan_id,
        "discoveryPlanDigest": discovery_plan_digest,
        "createdAt": created,
        "providerCounts": provider_counts,
        "candidateCount": len(candidates),
        "candidates": candidates,
    }
    catalog_digest = _digest(core)
    catalog = {
        "schema": "quwoquan_data.professional_image_governed_candidate_catalog",
        "catalogId": f"professional-image-governed-{catalog_digest[7:23]}",
        "catalogDigest": catalog_digest,
        **core,
    }
    assert_valid(
        catalog,
        "source",
        "professional_image_governed_candidate_catalog",
        label="professional image governed candidate catalog",
    )
    return catalog


def write_professional_image_governed_candidate_catalog(
    catalog: Mapping[str, Any], *, output_root: Path,
) -> Path:
    """Create-once write one governed catalog into its caller-owned root."""
    payload = dict(catalog)
    assert_valid(
        payload,
        "source",
        "professional_image_governed_candidate_catalog",
        label="professional image governed candidate catalog",
    )
    if payload.get("catalogDigest") != _digest(_catalog_core(payload)):
        _fail("governed candidate catalog digest drift")
    destination = output_root.expanduser().resolve() / f"{payload['catalogId']}.json"
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if destination.read_bytes() != body:
            _fail(f"governed candidate catalog collision: {destination}")
        return destination
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return destination


__all__ = [
    "CATALOG_REVISION",
    "GOVERNED_DISCOVERY_INVALID",
    "ProfessionalImageGovernedDiscoveryError",
    "build_professional_image_governed_candidate_catalog",
    "write_professional_image_governed_candidate_catalog",
]
