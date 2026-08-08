"""Canonical, digest-bound source-ready pools for scale campaigns.

This module is deliberately offline.  It freezes already-audited acquisition,
rights, quality and playability references; it never discovers or downloads
content and it never starts a campaign.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
SOURCE_POOL_INVALID = "DATA.SOURCE.POOL_INVALID"
SOURCE_POOL_CREATE_ONCE_COLLISION = "DATA.SOURCE.POOL_CREATE_ONCE_COLLISION"
SOURCE_POOL_EVIDENCE_INVALID = "DATA.SOURCE.POOL_EVIDENCE_INVALID"

_CARRIERS = ("homepage", "article", "image", "video")
_REQUIRED_NEW_COUNTS: dict[str, dict[str, int]] = {
    "M100": {"homepage": 180, "article": 180, "image": 180, "video": 18},
    "M1000": {"homepage": 1620, "article": 1620, "image": 1620, "video": 162},
    "M10000": {
        "homepage": 16200,
        "article": 16200,
        "image": 16200,
        "video": 1620,
    },
}
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PIN_ALIASES = frozenset({"pinterest", "pinterest.com", "www.pinterest.com"})
_TUCHONG_ALIASES = frozenset(
    {
        "tuchong",
        "tuchong.com",
        "www.tuchong.com",
        "图虫",
        "图虫社区",
        "图虫创意",
        "tuchong stock",
        "tuchong_stock_authorized",
    }
)


class ScaleSourcePoolError(ValueError):
    """Typed source-pool blocker."""

    def __init__(self, code: str, issues: Iterable[object]) -> None:
        normalized = tuple(str(issue).strip() for issue in issues if str(issue).strip())
        if not normalized:
            raise ValueError("scale source pool error requires an issue")
        self.code = code
        self.issues = normalized
        super().__init__(f"{code}: " + "; ".join(normalized))


def required_candidate_counts(target_scale: str) -> dict[str, int]:
    """Return the governed *new* oversampled pool for one milestone."""

    try:
        return dict(_REQUIRED_NEW_COUNTS[str(target_scale).strip()])
    except KeyError as exc:
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            [f"unsupported targetScale={target_scale!r}"],
        ) from exc


def _canonical_digest(document: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _normalized_provider(value: object) -> str:
    provider = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    provider = re.sub(r"\s+", " ", provider)
    if provider in _PIN_ALIASES:
        return "pinterest"
    if provider in _TUCHONG_ALIASES:
        return "tuchong"
    return provider


def _safe_ref(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            [f"{label} must be a non-empty relative reference"],
        )
    return path.as_posix()


def _identity(document: Mapping[str, Any]) -> tuple[str, str, str]:
    values = tuple(
        str(document.get(field) or "").strip()
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )
    if any(not _SHA256.fullmatch(value) for value in values):
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            ["sourceRevision/sourceDigest/entityCatalogDigest must be sha256"],
        )
    return values


def _binding_issues(candidate: Mapping[str, Any], *, candidate_id: str) -> list[str]:
    issues: list[str] = []
    for prefix in ("sourceUnit", "acquisition", "rights", "quality"):
        try:
            _safe_ref(candidate.get(f"{prefix}Ref"), label=f"{candidate_id}.{prefix}Ref")
        except ScaleSourcePoolError as exc:
            issues.extend(exc.issues)
        digest = str(candidate.get(f"{prefix}Digest") or "").strip()
        if not _SHA256.fullmatch(digest):
            issues.append(f"{candidate_id}.{prefix}Digest is not sha256")
        file_digest = str(candidate.get(f"{prefix}FileSha256") or "").strip()
        if not _SHA256.fullmatch(file_digest):
            issues.append(f"{candidate_id}.{prefix}FileSha256 is not sha256")
    return issues


def _video_issues(candidate: Mapping[str, Any], *, candidate_id: str) -> list[str]:
    readiness = candidate.get("videoReadiness")
    if not isinstance(readiness, Mapping):
        return [f"{candidate_id} lacks videoReadiness"]
    issues: list[str] = []
    try:
        _safe_ref(candidate.get("playabilityRef"), label=f"{candidate_id}.playabilityRef")
    except ScaleSourcePoolError as exc:
        issues.extend(exc.issues)
    if not _SHA256.fullmatch(str(candidate.get("playabilityDigest") or "").strip()):
        issues.append(f"{candidate_id}.playabilityDigest is not sha256")
    if not _SHA256.fullmatch(
        str(candidate.get("playabilityFileSha256") or "").strip()
    ):
        issues.append(f"{candidate_id}.playabilityFileSha256 is not sha256")
    if any(readiness.get(field) is not True for field in ("playable", "motion", "premiumEligible")):
        issues.append(f"{candidate_id} is not playable motion Premium media")
    for field in ("playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"):
        value = readiness.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            issues.append(f"{candidate_id}.{field} is incomplete")
    if not str(readiness.get("observedAt") or "").strip():
        issues.append(f"{candidate_id}.observedAt is missing")
    percentile = readiness.get("popularityPercentile")
    if (
        isinstance(percentile, bool)
        or not isinstance(percentile, (int, float))
        or not 0 <= float(percentile) <= 1
    ):
        issues.append(f"{candidate_id}.popularityPercentile is invalid")
    comparison = readiness.get("comparisonBucket")
    if not isinstance(comparison, Mapping):
        issues.append(f"{candidate_id}.comparisonBucket is missing")
    else:
        if _normalized_provider(comparison.get("provider")) != _normalized_provider(
            candidate.get("provider")
        ):
            issues.append(f"{candidate_id}.comparisonBucket provider drift")
        if any(
            not str(comparison.get(field) or "").strip()
            for field in ("topic", "timeBucket")
        ):
            issues.append(f"{candidate_id}.comparisonBucket is incomplete")
        count = comparison.get("candidateCount")
        if isinstance(count, bool) or not isinstance(count, int) or count < 2:
            issues.append(f"{candidate_id}.comparisonBucket lacks comparable candidates")
    return issues


def _image_mix(counts: Counter[str], *, total: int) -> tuple[dict[str, Any], list[str]]:
    pinterest = counts["pinterest"]
    tuchong = counts["tuchong"]
    professional = pinterest + tuchong
    issues: list[str] = []
    largest_other = max(
        (count for provider, count in counts.items() if provider != "pinterest"),
        default=0,
    )
    if pinterest <= largest_other:
        issues.append("image pool Pinterest must be the unique largest provider")
    if tuchong < 1:
        issues.append("image pool Tuchong count must be positive")
    if professional * 2 < total:
        issues.append("image pool Pinterest+Tuchong ratio is below 50%")
    dominant = sorted(
        provider for provider, count in counts.items() if count * 10 > total * 7
    )
    if dominant:
        issues.append("image pool single-provider ratio exceeds 70%: " + ", ".join(dominant))
    rows = [
        {
            "provider": provider,
            "candidateCount": count,
            "candidateRatio": round(count / total, 6) if total else 0.0,
        }
        for provider, count in sorted(counts.items())
    ]
    return (
        {
            "totalCandidateCount": total,
            "pinterestCandidateCount": pinterest,
            "tuchongCandidateCount": tuchong,
            "pinterestTuchongCandidateRatio": (
                round(professional / total, 6) if total else 0.0
            ),
            "largestProvider": "pinterest" if not issues else "",
            "maxProviderCandidateRatio": max(
                (round(count / total, 6) for count in counts.values()),
                default=0.0,
            ),
            "providerCandidateCounts": rows,
        },
        issues,
    )


def _assert_pool_document(plan: Mapping[str, Any]) -> tuple[str, str, str]:
    try:
        assert_valid(dict(plan), "source", "scale_source_pool", label="scale source pool")
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ScaleSourcePoolError(SOURCE_POOL_INVALID, [str(exc)]) from exc
    stable = {key: value for key, value in plan.items() if key != "planDigest"}
    if plan.get("planDigest") != _canonical_digest(stable):
        raise ScaleSourcePoolError(SOURCE_POOL_INVALID, ["planDigest mismatch"])
    return _identity(plan)


def validate_scale_source_pool(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one immutable source-ready pool and return derived evidence."""

    plan_identity = _assert_pool_document(plan)
    required = required_candidate_counts(str(plan["targetScale"]))
    declared_required = {
        str(row["carrier"]): int(row["minimumCandidateCount"])
        for row in plan["requiredNewCandidateCounts"]
    }
    if declared_required != required:
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            ["requiredNewCandidateCounts drift from governed milestone"],
        )

    issues: list[str] = []
    counts: Counter[str] = Counter()
    image_providers: Counter[str] = Counter()
    candidate_ids: set[str] = set()
    object_refs: set[str] = set()
    content_digests: set[str] = set()
    duplicate_count = 0
    entity_mismatch_count = 0
    for raw in plan["candidates"]:
        candidate = dict(raw)
        candidate_id = str(candidate["candidateId"]).strip()
        carrier = str(candidate["carrier"])
        counts[carrier] += 1
        if _identity(candidate) != plan_identity:
            issues.append(f"{candidate_id} source identity drift")
        issues.extend(_binding_issues(candidate, candidate_id=candidate_id))
        object_ref = str(candidate["objectRef"]).strip()
        content_digest = str(candidate["contentSha256"]).strip()
        if (
            candidate_id in candidate_ids
            or object_ref in object_refs
            or content_digest in content_digests
        ):
            duplicate_count += 1
        candidate_ids.add(candidate_id)
        object_refs.add(object_ref)
        content_digests.add(content_digest)
        if candidate["entityRef"] != candidate["observedEntityRef"]:
            entity_mismatch_count += 1
        if candidate["acquisitionStatus"] != "acquired":
            issues.append(f"{candidate_id} is not acquired")
        if candidate["rightsStatus"] == "restricted":
            issues.append(f"{candidate_id} has restricted rights")
        if candidate["distributionDecision"] not in {
            "research_allowed",
            "commercial_allowed",
        }:
            issues.append(f"{candidate_id} is not distribution-ready")
        if candidate["qualityStatus"] != "passed":
            issues.append(f"{candidate_id} quality is not passed")
        if carrier in {"image", "video"} and candidate["generated"] is not False:
            issues.append(f"{candidate_id} generated media is forbidden")
        if carrier == "image":
            image_providers[_normalized_provider(candidate["provider"])] += 1
        if carrier == "video":
            issues.extend(_video_issues(candidate, candidate_id=candidate_id))
        elif any(
            candidate[field] is not None
            for field in (
                "playabilityRef",
                "playabilityDigest",
                "playabilityFileSha256",
            )
        ):
            issues.append(f"{candidate_id} non-video playability evidence must be null")

    for carrier in _CARRIERS:
        if counts[carrier] < required[carrier]:
            issues.append(
                f"{carrier} source-ready pool shortfall: "
                f"required={required[carrier]} actual={counts[carrier]}"
            )
    if duplicate_count:
        issues.append(f"cross-carrier duplicateCount={duplicate_count}, required=0")
    if entity_mismatch_count:
        issues.append(f"entityMismatchCount={entity_mismatch_count}, required=0")
    image_mix, image_issues = _image_mix(
        image_providers,
        total=counts["image"],
    )
    issues.extend(image_issues)
    if issues:
        raise ScaleSourcePoolError(SOURCE_POOL_SHORTFALL, issues)
    return {
        "schema": "quwoquan_data.scale_source_pool_validation",
        "poolId": plan["poolId"],
        "targetScale": plan["targetScale"],
        "planDigest": plan["planDigest"],
        "sourceRevision": plan["sourceRevision"],
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
        "candidateCounts": [
            {
                "carrier": carrier,
                "minimumCandidateCount": required[carrier],
                "actualCandidateCount": counts[carrier],
            }
            for carrier in _CARRIERS
        ],
        "duplicateCount": 0,
        "entityMismatchCount": 0,
        "professionalImageSourceMix": image_mix,
        "videoPopularityReadyCount": counts["video"],
        "videoPlayableMotionPremiumCount": counts["video"],
        "decision": "GO",
    }


def _evidence_root(path: Path) -> Path:
    root = path.expanduser().absolute()
    try:
        mode = root.lstat().st_mode
    except OSError as exc:
        raise ScaleSourcePoolError(
            SOURCE_POOL_EVIDENCE_INVALID,
            [f"evidence root is missing or unreadable: {root}"],
        ) from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ScaleSourcePoolError(
            SOURCE_POOL_EVIDENCE_INVALID,
            [f"evidence root must be a real directory: {root}"],
        )
    return root


def _evidence_file(path: Path, ref: object, *, label: str) -> Path:
    try:
        relative = Path(_safe_ref(ref, label=label))
    except ScaleSourcePoolError as exc:
        raise ScaleSourcePoolError(SOURCE_POOL_EVIDENCE_INVALID, exc.issues) from exc
    current = path
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise ScaleSourcePoolError(
                SOURCE_POOL_EVIDENCE_INVALID,
                [f"{label} file is missing or unreadable: {relative.as_posix()}"],
            ) from exc
        if stat.S_ISLNK(mode):
            raise ScaleSourcePoolError(
                SOURCE_POOL_EVIDENCE_INVALID,
                [f"{label} must not traverse a symlink: {relative.as_posix()}"],
            )
        final = index == len(relative.parts) - 1
        if (not final and not stat.S_ISDIR(mode)) or (
            final and not stat.S_ISREG(mode)
        ):
            raise ScaleSourcePoolError(
                SOURCE_POOL_EVIDENCE_INVALID,
                [f"{label} is not a regular evidence file: {relative.as_posix()}"],
            )
    return current


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ScaleSourcePoolError(
            SOURCE_POOL_EVIDENCE_INVALID,
            [f"evidence file became unreadable: {path}"],
        ) from exc
    return "sha256:" + digest.hexdigest()


def validate_scale_source_pool_evidence(
    plan: Mapping[str, Any], *, evidence_root: Path
) -> dict[str, Any]:
    """Validate every immutable evidence ref against physical bytes."""

    try:
        _assert_pool_document(plan)
    except ScaleSourcePoolError as exc:
        raise ScaleSourcePoolError(SOURCE_POOL_EVIDENCE_INVALID, exc.issues) from exc
    root = _evidence_root(evidence_root)
    computed: dict[str, str] = {}
    binding_count = 0
    for candidate in plan["candidates"]:
        candidate_id = str(candidate["candidateId"])
        prefixes = ["sourceUnit", "acquisition", "rights", "quality"]
        if candidate["carrier"] == "video":
            prefixes.append("playability")
        elif any(
            candidate[field] is not None
            for field in (
                "playabilityRef",
                "playabilityDigest",
                "playabilityFileSha256",
            )
        ):
            raise ScaleSourcePoolError(
                SOURCE_POOL_EVIDENCE_INVALID,
                [f"{candidate_id} non-video playability evidence must be null"],
            )
        for prefix in prefixes:
            ref_field = f"{prefix}Ref"
            sha_field = f"{prefix}FileSha256"
            expected = str(candidate.get(sha_field) or "")
            if not _SHA256.fullmatch(expected):
                raise ScaleSourcePoolError(
                    SOURCE_POOL_EVIDENCE_INVALID,
                    [f"{candidate_id}.{sha_field} is not sha256"],
                )
            file_path = _evidence_file(
                root,
                candidate.get(ref_field),
                label=f"{candidate_id}.{ref_field}",
            )
            ref = file_path.relative_to(root).as_posix()
            if ref not in computed:
                computed[ref] = _file_sha256(file_path)
            actual = computed[ref]
            if actual != expected:
                raise ScaleSourcePoolError(
                    SOURCE_POOL_EVIDENCE_INVALID,
                    [
                        f"{candidate_id}.{sha_field} drift: "
                        f"expected={expected} actual={actual}"
                    ],
                )
            binding_count += 1
    validation = validate_scale_source_pool(plan)
    return {
        **validation,
        "evidenceBindingCount": binding_count,
        "evidenceFileCount": len(computed),
        "evidenceFileSha256Verified": True,
    }


def build_scale_source_pool_plan(
    *,
    pool_id: str,
    target_scale: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    created_at: str,
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build and validate a deterministic source-ready pool document."""

    required = required_candidate_counts(target_scale)
    ordered = sorted(
        (dict(candidate) for candidate in candidates),
        key=lambda row: (str(row.get("carrier")), str(row.get("objectRef"))),
    )
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.scale_source_pool",
        "poolId": str(pool_id).strip(),
        "targetScale": target_scale,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "createdAt": created_at,
        "requiredNewCandidateCounts": [
            {"carrier": carrier, "minimumCandidateCount": required[carrier]}
            for carrier in _CARRIERS
        ],
        "candidates": ordered,
    }
    document = {**stable, "planDigest": _canonical_digest(stable)}
    validate_scale_source_pool(document)
    return document


def write_create_once_scale_source_pool(
    destination: Path,
    plan: Mapping[str, Any],
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    """Persist one digest-bound plan without overwriting any prior receipt."""

    validate_scale_source_pool_evidence(plan, evidence_root=evidence_root)
    body = json.dumps(
        dict(plan), ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
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
            existing = read_json(destination)
            if not isinstance(existing, dict):
                raise ScaleSourcePoolError(
                    SOURCE_POOL_CREATE_ONCE_COLLISION,
                    [f"existing pool is not an object: {destination}"],
                )
            try:
                validate_scale_source_pool_evidence(
                    existing,
                    evidence_root=evidence_root,
                )
            except ScaleSourcePoolError as exc:
                raise ScaleSourcePoolError(
                    SOURCE_POOL_CREATE_ONCE_COLLISION,
                    [f"existing pool is invalid: {exc}"],
                ) from exc
            if existing.get("planDigest") != plan.get("planDigest") or existing != dict(plan):
                raise ScaleSourcePoolError(
                    SOURCE_POOL_CREATE_ONCE_COLLISION,
                    [f"scale source pool create-once collision: {destination}"],
                )
            return existing
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return dict(plan)


__all__ = [
    "SOURCE_POOL_CREATE_ONCE_COLLISION",
    "SOURCE_POOL_EVIDENCE_INVALID",
    "SOURCE_POOL_INVALID",
    "SOURCE_POOL_SHORTFALL",
    "ScaleSourcePoolError",
    "build_scale_source_pool_plan",
    "required_candidate_counts",
    "validate_scale_source_pool",
    "validate_scale_source_pool_evidence",
    "write_create_once_scale_source_pool",
]
