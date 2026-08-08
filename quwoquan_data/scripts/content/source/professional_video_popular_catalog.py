"""Offline popular-video metadata and manual-file candidate catalog."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from core.paths import CONTROL_PLANE_SHARED_ROOT, REPO_ROOT
from core.schema import assert_valid

from content.source.professional_video_popularity import popularity_score
from content.source.professional_video_probe import probe_professional_video

POLICY_PATH = (
    CONTROL_PLANE_SHARED_ROOT / "catalogs" / "professional_video_popular_sources.yaml"
)
POPULAR_VIDEO_INVALID = "DATA.SOURCE.POOL_INVALID"
POPULAR_VIDEO_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
_REVISION = "popular-video-candidates-v1"
_COUNT_FIELDS = (
    "playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"
)
_FORBIDDEN_KEYS = frozenset({
    "asseturl", "streamurl", "downloadurl", "playurl", "cookie", "cookies",
    "authorization", "token", "drmlicense", "videobody", "mediaurl",
})
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class ProfessionalVideoPopularCatalogError(ValueError):
    """Typed candidate-catalog blocker."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(message: str, *, shortfall: bool = False) -> None:
    raise ProfessionalVideoPopularCatalogError(
        POPULAR_VIDEO_SHORTFALL if shortfall else POPULAR_VIDEO_INVALID,
        message,
    )


def _digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _catalog_core(catalog: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in catalog.items()
        if key not in {"catalogId", "catalogDigest"}
    }


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_file(root: Path, ref: object) -> tuple[Path, str]:
    return _safe_relative_file(root, ref, label="manualFileRef")


def _safe_relative_file(
    root: Path,
    ref: object,
    *,
    label: str,
) -> tuple[Path, str]:
    relative = Path(str(ref or "").strip())
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail(f"{label} must be a safe relative reference")
    current = root.resolve()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail(f"{label} must not traverse a symlink")
    if not current.is_file():
        _fail(f"{label} is missing: {relative.as_posix()}")
    return current, relative.as_posix()


def _https(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    parsed = urlsplit(text)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        _fail(f"{label} must be anonymous HTTPS")
    return text


def _host_matches(url: str, roots: Iterable[str]) -> bool:
    host = str(urlsplit(url).hostname or "").casefold()
    return any(host == root or host.endswith("." + root) for root in roots)


def _assert_no_stream_or_secret(value: object, *, label: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).replace("_", "").casefold() in _FORBIDDEN_KEYS:
                _fail(f"{label} contains forbidden stream/credential field: {key}")
            _assert_no_stream_or_secret(child, label=label)
    elif isinstance(value, list):
        for child in value:
            _assert_no_stream_or_secret(child, label=label)


def _load_policy(path: Path) -> tuple[dict[str, Any], str, str]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        _fail(f"popular-video provider policy is missing: {resolved}")
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        _fail("popular-video provider policy must be an object")
    try:
        assert_valid(
            payload,
            "source",
            "professional_video_popular_provider_catalog",
            label="popular-video provider policy",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        _fail(str(exc))
    providers = [str(row["provider"]) for row in payload["providers"]]
    if providers != list(payload["providerOrder"]):
        _fail("popular-video providerOrder must equal provider rows")
    priorities = [int(row["priority"]) for row in payload["providers"]]
    if priorities != list(range(len(priorities))):
        _fail("popular-video provider priorities must be contiguous")
    try:
        ref = resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        _fail("popular-video provider policy must be version controlled")
        raise AssertionError("unreachable") from exc
    return payload, ref, _digest(payload)


def _metadata_rows(
    responses: Iterable[Mapping[str, Any]], *, policies: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    seen_responses: set[str] = set()
    for response in responses:
        if not isinstance(response, Mapping):
            _fail("supported API metadata response must be an object")
        _assert_no_stream_or_secret(response, label="supported API metadata response")
        provider = str(response.get("provider") or "").strip().casefold()
        policy = policies.get(provider)
        if policy is None:
            _fail(f"unsupported popular-video provider: {provider}")
        page = _https(response.get("sourcePageUrl"), label="sourcePageUrl")
        api_evidence = _https(response.get("apiEvidenceUrl"), label="apiEvidenceUrl")
        roots = [str(value).casefold() for value in policy["sourceHosts"]]
        if not _host_matches(page, roots) or not _host_matches(api_evidence, roots):
            _fail(f"{provider} API/source host does not match production policy")
        status = response.get("statusCode")
        content_type = str(response.get("contentType") or "").split(";", 1)[0].strip().casefold()
        access = response.get("accessEvidence")
        expected_access = {
            "supportedApi": True,
            "cookiesSent": False,
            "loginRequired": False,
            "paywallRequired": False,
            "drmProtected": False,
            "accessControlBypass": False,
        }
        if (
            isinstance(status, bool) or not isinstance(status, int) or not 200 <= status < 300
            or content_type != "application/json"
            or not isinstance(access, Mapping)
            or dict(access) != expected_access
        ):
            _fail(f"{provider} metadata did not come from an allowed supported API")
        items = response.get("items")
        if not isinstance(items, list) or not items:
            _fail(f"{provider} supported API metadata has no candidates", shortfall=True)
        response_digest = _digest(dict(response))
        if response_digest in seen_responses:
            _fail(f"duplicate supported API metadata response: {provider}")
        seen_responses.add(response_digest)
        sources.append({
            "provider": provider,
            "sourcePageUrl": page,
            "apiEvidenceUrl": api_evidence,
            "responseDigest": response_digest,
            "candidateCount": len(items),
        })
        for item in items:
            if not isinstance(item, Mapping):
                _fail(f"{provider} metadata candidate must be an object")
            required_text = (
                "sourceId", "entityId", "observedEntityId", "creator", "title",
                "observedAt", "topic", "timeBucket",
            )
            if any(not str(item.get(field) or "").strip() for field in required_text):
                _fail(f"{provider} metadata candidate identity is incomplete", shortfall=True)
            if str(item["entityId"]).strip() != str(item["observedEntityId"]).strip():
                _fail(
                    f"{provider}:{item.get('sourceId')} observed entity does not match",
                    shortfall=True,
                )
            counts: dict[str, int] = {}
            for field in _COUNT_FIELDS:
                value = item.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    _fail(f"{provider}:{item.get('sourceId')} lacks {field}", shortfall=True)
                counts[field] = value
            score = popularity_score(counts)
            if score is None:
                _fail(f"{provider}:{item.get('sourceId')} popularity is incomplete", shortfall=True)
            rows.append({
                "provider": provider,
                "sourceId": str(item["sourceId"]).strip(),
                "entityId": str(item["entityId"]).strip(),
                "observedEntityId": str(item["observedEntityId"]).strip(),
                "sourcePageUrl": page,
                "creator": str(item["creator"]).strip(),
                "title": str(item["title"]).strip(),
                "observedAt": str(item["observedAt"]).strip(),
                "topic": str(item["topic"]).strip(),
                "timeBucket": str(item["timeBucket"]).strip(),
                "popularity": {**counts, "popularityScore": score},
                "metadataResponseDigest": response_digest,
            })
    return rows, sources


def _rank(rows: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["provider"], row["topic"], row["timeBucket"])].append(row)
    for key, group in groups.items():
        if len(group) < 2:
            _fail(f"popularity comparison bucket has fewer than two candidates: {key}", shortfall=True)
        scores = [int(row["popularity"]["popularityScore"]) for row in group]
        for row, score in zip(group, scores, strict=True):
            lower = sum(candidate < score for candidate in scores)
            equal = sum(candidate == score for candidate in scores)
            row["popularity"].update(
                popularityPercentile=round((lower + (equal - 1) / 2) / (len(group) - 1), 6),
                comparisonCandidateCount=len(group),
            )


def _manual_files(
    manifests: Iterable[Mapping[str, Any]], *, root: Path, policies: Mapping[str, Mapping[str, Any]]
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    content_seen: dict[str, tuple[str, str]] = {}
    for manifest in manifests:
        if not isinstance(manifest, Mapping):
            _fail("manual video manifest must be an object")
        if set(manifest) != {"provider", "sourceId", "sourcePageUrl", "manualFileRef"}:
            _fail("manual video manifest contains unsupported fields")
        provider = str(manifest.get("provider") or "").strip().casefold()
        source_id = str(manifest.get("sourceId") or "").strip()
        policy = policies.get(provider)
        if policy is None or not source_id:
            _fail("manual video manifest provider/sourceId is invalid")
        page = _https(manifest.get("sourcePageUrl"), label="manual sourcePageUrl")
        if not _host_matches(page, [str(value).casefold() for value in policy["sourceHosts"]]):
            _fail("manual video sourcePageUrl host violates provider policy")
        path, ref = _safe_file(root, manifest.get("manualFileRef"))
        probe = probe_professional_video(path)
        if not all((
            probe.get("playable") is True,
            probe.get("motionVideo") is True,
            probe.get("staticImageSequence") is False,
            probe.get("premiumPlayableEligible") is True,
        )):
            _fail(f"manual video is not playable motion media: {ref}")
        digest = _file_digest(path)
        key = (provider, source_id)
        if key in result:
            _fail(f"duplicate manual manifest: {provider}:{source_id}")
        if digest in content_seen:
            _fail(f"duplicate manual video bytes: {ref}")
        content_seen[digest] = key
        result[key] = {
            "sourcePageUrl": page,
            "manualFileRef": ref,
            "manualFileSha256": digest,
            "manualFileBytes": path.stat().st_size,
            "mediaProbe": probe,
        }
    return result


def build_professional_video_popular_candidate_catalog(
    *,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    metadata_responses: Iterable[Mapping[str, Any]],
    manual_file_manifests: Iterable[Mapping[str, Any]],
    evidence_root: Path,
    provider_policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    """Build candidate metadata only; never download or mark media acquired."""
    identity = (source_revision, source_digest, entity_catalog_digest)
    if any(not _SHA256.fullmatch(value) for value in identity):
        _fail("sourceRevision/sourceDigest/entityCatalogDigest must be sha256 digests")
    policy, policy_ref, policy_digest = _load_policy(provider_policy_path)
    policies = {str(row["provider"]): row for row in policy["providers"]}
    rows, source_responses = _metadata_rows(metadata_responses, policies=policies)
    if not rows:
        _fail("popular-video candidate pool is empty", shortfall=True)
    keys = [(row["provider"], row["sourceId"]) for row in rows]
    if len(keys) != len(set(keys)):
        _fail("popular-video provider/sourceId values are not unique")
    _rank(rows)
    manuals = _manual_files(
        manual_file_manifests, root=evidence_root.expanduser().resolve(), policies=policies
    )
    for key in manuals:
        if key not in set(keys):
            _fail(f"manual video manifest lacks metadata candidate: {key[0]}:{key[1]}")
    candidates: list[dict[str, Any]] = []
    for row in rows:
        key = (row["provider"], row["sourceId"])
        manual = manuals.get(key)
        if manual is not None and manual["sourcePageUrl"] != row["sourcePageUrl"]:
            _fail(f"manual video source page drift: {key[0]}:{key[1]}")
        seed = _digest({field: row[field] for field in ("provider", "sourceId", "metadataResponseDigest")})
        candidates.append({
            "candidateId": f"popular-video:{row['provider']}:{seed[7:23]}",
            **row,
            "manualFileRequired": True,
            "manualFileProvided": manual is not None,
            "manualFileRef": manual["manualFileRef"] if manual else None,
            "manualFileSha256": manual["manualFileSha256"] if manual else None,
            "manualFileBytes": manual["manualFileBytes"] if manual else None,
            "mediaProbe": manual["mediaProbe"] if manual else None,
            "acquisitionStatus": "not_acquired",
        })
    order = {provider: index for index, provider in enumerate(policy["providerOrder"])}
    candidates.sort(key=lambda row: (
        order[row["provider"]], row["topic"], row["timeBucket"],
        -float(row["popularity"]["popularityPercentile"]), row["sourceId"],
    ))
    counts = Counter(row["provider"] for row in candidates)
    manual_counts = Counter(row["provider"] for row in candidates if row["manualFileProvided"])
    provider_counts = [
        {
            "provider": provider,
            "displayName": str(policies[provider]["displayName"]),
            "candidateCount": counts[provider],
            "manualFileProvidedCount": manual_counts[provider],
        }
        for provider in policy["providerOrder"] if counts[provider]
    ]
    provider_projection = [
        {
            "provider": row["provider"], "displayName": row["displayName"],
            "priority": row["priority"], "manualFileRequired": True,
            "automaticStreamParsing": False, "automaticVideoDownload": False,
        }
        for row in policy["providers"] if counts[row["provider"]]
    ]
    stable = {
        "schema": "quwoquan_data.professional_video_popular_candidate_catalog",
        "catalogRevision": _REVISION,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "providerPolicyRef": policy_ref,
        "providerPolicyDigest": policy_digest,
        "providerPolicies": provider_projection,
        "sourceResponses": sorted(source_responses, key=lambda row: (row["provider"], row["responseDigest"])),
        "providerCounts": provider_counts,
        "candidateCount": len(candidates),
        "candidates": candidates,
    }
    catalog_digest = _digest(stable)
    document = {
        "schema": stable["schema"],
        "catalogId": f"popular-video-candidates-{catalog_digest[7:23]}",
        **{key: value for key, value in stable.items() if key != "schema"},
        "catalogDigest": catalog_digest,
    }
    try:
        assert_valid(
            document,
            "source",
            "professional_video_popular_candidate_catalog",
            label="popular-video candidate catalog",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        _fail(str(exc))
    return document


def write_create_once_professional_video_popular_candidate_catalog(
    destination: Path,
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one identity-bound popular-video catalog without replacement."""
    payload = dict(catalog)
    try:
        assert_valid(
            payload,
            "source",
            "professional_video_popular_candidate_catalog",
            label="popular-video candidate catalog",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        _fail(str(exc))
    if payload.get("catalogDigest") != _digest(_catalog_core(payload)):
        _fail("popular-video candidate catalog digest drift")
    body = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_bytes() != body:
                _fail(f"popular-video catalog create-once collision: {destination}")
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return payload


def load_professional_video_popular_candidate_catalog(
    catalog_ref: str,
    *,
    root: Path,
    expected_catalog_digest: str,
    expected_file_sha256: str,
    expected_identity: tuple[str, str, str],
) -> dict[str, Any]:
    """Load one canonical relative catalog and re-derive every frozen identity."""
    path, ref = _safe_relative_file(root, catalog_ref, label="popularCatalogRef")
    expected_ref = (
        "professional-video-popular-catalogs/"
        f"{expected_catalog_digest.removeprefix('sha256:')}.json"
    )
    if ref != expected_ref:
        _fail(f"popularCatalogRef is not canonical: {ref}")
    if not _SHA256.fullmatch(expected_catalog_digest) or not _SHA256.fullmatch(
        expected_file_sha256
    ):
        _fail("popular catalog digest/file SHA must be sha256 digests")
    if _file_digest(path) != expected_file_sha256:
        _fail(f"popular-video catalog file SHA drift: {ref}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(f"popular-video catalog is not readable JSON: {ref}: {exc}")
    if not isinstance(payload, dict):
        _fail(f"popular-video catalog must be an object: {ref}")
    try:
        assert_valid(
            payload,
            "source",
            "professional_video_popular_candidate_catalog",
            label="popular-video candidate catalog",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        _fail(str(exc))
    if payload.get("catalogDigest") != expected_catalog_digest or _digest(
        _catalog_core(payload)
    ) != expected_catalog_digest:
        _fail(f"popular-video catalog digest drift: {ref}")
    actual_identity = tuple(
        str(payload.get(field) or "")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )
    if actual_identity != expected_identity:
        _fail(f"popular-video catalog source identity drift: {ref}")
    candidate_ids = [str(row["candidateId"]) for row in payload["candidates"]]
    if len(candidate_ids) != len(set(candidate_ids)):
        _fail(f"popular-video catalog candidateId values are not unique: {ref}")
    return payload


__all__ = [
    "POLICY_PATH", "POPULAR_VIDEO_INVALID", "POPULAR_VIDEO_SHORTFALL",
    "ProfessionalVideoPopularCatalogError",
    "build_professional_video_popular_candidate_catalog",
    "load_professional_video_popular_candidate_catalog",
    "write_create_once_professional_video_popular_candidate_catalog",
]
