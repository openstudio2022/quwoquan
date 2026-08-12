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
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid
from core.source_attribution import canonical_source_attribution

from content.source.research.scale_source_pool_evidence_path import (
    ScaleSourcePoolEvidencePathError,
    compute_evidence_file_sha256,
    resolve_evidence_directory,
    resolve_evidence_file,
    resolve_evidence_root,
)

SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
SOURCE_POOL_INVALID = "DATA.SOURCE.POOL_INVALID"
SOURCE_POOL_CREATE_ONCE_COLLISION = "DATA.SOURCE.POOL_CREATE_ONCE_COLLISION"
SOURCE_POOL_EVIDENCE_INVALID = "DATA.SOURCE.POOL_EVIDENCE_INVALID"

_CARRIERS = ("homepage", "article", "image", "video")
_MILESTONES = frozenset({"M100", "M1000", "M10000"})
_DEFAULT_WAVE_CANDIDATE_COUNTS = {
    "homepage": 12,
    "article": 12,
    "image": 12,
    "video": 12,
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
    """Return the planning default for one rolling wave, never a milestone gate."""

    if str(target_scale).strip() not in _MILESTONES:
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            [f"unsupported targetScale={target_scale!r}"],
        )
    return dict(_DEFAULT_WAVE_CANDIDATE_COUNTS)


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
    if candidate.get("carrier") in {"homepage", "article"} or (
        candidate.get("sourceAttribution") is not None
    ):
        try:
            canonical_source_attribution(candidate.get("sourceAttribution"))
        except ValueError as exc:
            issues.append(f"{candidate_id}.sourceAttribution is incomplete: {exc}")
    root_ref = candidate.get("sourceReadyEvidenceRootRef")
    if candidate.get("carrier") in {"homepage", "article"} or root_ref is not None:
        try:
            _safe_ref(root_ref, label=f"{candidate_id}.sourceReadyEvidenceRootRef")
        except ScaleSourcePoolError as exc:
            issues.extend(exc.issues)
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
    if any(readiness.get(field) is not True for field in ("playable", "motion")):
        issues.append(f"{candidate_id} is not playable motion media")
    return issues


def _video_popularity_ready(candidate: Mapping[str, Any]) -> bool:
    readiness = candidate.get("videoReadiness")
    if not isinstance(readiness, Mapping):
        return False
    for field in ("playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"):
        value = readiness.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
    if not str(readiness.get("observedAt") or "").strip():
        return False
    percentile = readiness.get("popularityPercentile")
    if (
        isinstance(percentile, bool)
        or not isinstance(percentile, (int, float))
        or not 0 <= float(percentile) <= 1
    ):
        return False
    comparison = readiness.get("comparisonBucket")
    if not isinstance(comparison, Mapping):
        return False
    if _normalized_provider(comparison.get("provider")) != _normalized_provider(
        candidate.get("provider")
    ):
        return False
    if any(
        not str(comparison.get(field) or "").strip()
        for field in ("topic", "timeBucket")
    ):
        return False
    count = comparison.get("candidateCount")
    return not isinstance(count, bool) and isinstance(count, int) and count >= 2


def _image_mix(counts: Counter[str], *, total: int) -> dict[str, Any]:
    pinterest = counts["pinterest"]
    tuchong = counts["tuchong"]
    professional = pinterest + tuchong
    largest_other = max(
        (count for provider, count in counts.items() if provider != "pinterest"),
        default=0,
    )
    dominant = sorted(
        provider for provider, count in counts.items() if count * 10 > total * 7
    )
    rows = [
        {
            "provider": provider,
            "candidateCount": count,
            "candidateRatio": round(count / total, 6) if total else 0.0,
        }
        for provider, count in sorted(counts.items())
    ]
    largest_provider = (
        min(
            provider
            for provider, count in counts.items()
            if count == max(counts.values())
        )
        if counts
        else ""
    )
    return {
        "totalCandidateCount": total,
        "pinterestCandidateCount": pinterest,
        "tuchongCandidateCount": tuchong,
        "pinterestTuchongCandidateRatio": (
            round(professional / total, 6) if total else 0.0
        ),
        "largestProvider": largest_provider,
        "maxProviderCandidateRatio": max(
            (round(count / total, 6) for count in counts.values()),
            default=0.0,
        ),
        "providerCandidateCounts": rows,
        "policyObservations": {
            "pinterestUniqueLargest": bool(pinterest > largest_other),
            "tuchongPresent": bool(tuchong),
            "pinterestTuchongAtLeastHalf": bool(total and professional * 2 >= total),
            "providerAboveSeventyPercent": dominant,
        },
    }


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
    declared_wave = {
        str(row["carrier"]): int(row["minimumCandidateCount"])
        for row in plan["waveCandidateCounts"]
    }

    issues: list[str] = []
    counts: Counter[str] = Counter()
    image_providers: Counter[str] = Counter()
    candidate_ids: set[str] = set()
    object_refs: set[str] = set()
    content_digests: set[str] = set()
    duplicate_count = 0
    entity_mismatch_count = 0
    video_popularity_ready_count = 0
    video_premium_eligible_count = 0
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
            video_popularity_ready_count += int(_video_popularity_ready(candidate))
            readiness = candidate.get("videoReadiness")
            video_premium_eligible_count += int(
                isinstance(readiness, Mapping)
                and readiness.get("premiumEligible") is True
            )
        elif any(
            candidate[field] is not None
            for field in (
                "playabilityRef",
                "playabilityDigest",
                "playabilityFileSha256",
            )
        ):
            issues.append(f"{candidate_id} non-video playability evidence must be null")

    actual_wave = {carrier: counts[carrier] for carrier in _CARRIERS}
    if declared_wave != actual_wave:
        issues.append(
            "waveCandidateCounts drift from current physical candidates: "
            f"declared={declared_wave} actual={actual_wave}"
        )
    if duplicate_count:
        issues.append(f"cross-carrier duplicateCount={duplicate_count}, required=0")
    if entity_mismatch_count:
        issues.append(f"entityMismatchCount={entity_mismatch_count}, required=0")
    image_mix = _image_mix(
        image_providers,
        total=counts["image"],
    )
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
                "minimumCandidateCount": declared_wave[carrier],
                "actualCandidateCount": counts[carrier],
            }
            for carrier in _CARRIERS
        ],
        "duplicateCount": 0,
        "entityMismatchCount": 0,
        "professionalImageSourceMix": image_mix,
        "videoPopularityReadyCount": video_popularity_ready_count,
        "videoPlayableMotionCount": counts["video"],
        "videoPremiumEligibleCount": video_premium_eligible_count,
        "decision": "GO",
    }


def _candidate_evidence_root(
    root: Path, candidate: Mapping[str, Any], *, candidate_id: str
) -> Path:
    root_ref = candidate.get("sourceReadyEvidenceRootRef")
    if root_ref is None:
        return root
    return resolve_evidence_directory(
        root,
        root_ref,
        label=f"{candidate_id}.sourceReadyEvidenceRootRef",
    )


def validate_scale_source_pool_evidence(
    plan: Mapping[str, Any], *, evidence_root: Path
) -> dict[str, Any]:
    """Validate every immutable evidence ref against physical bytes."""

    try:
        _assert_pool_document(plan)
    except ScaleSourcePoolError as exc:
        raise ScaleSourcePoolError(SOURCE_POOL_EVIDENCE_INVALID, exc.issues) from exc
    try:
        root = resolve_evidence_root(evidence_root)
        computed: dict[str, str] = {}
        binding_count = 0
        for candidate in plan["candidates"]:
            candidate_id = str(candidate["candidateId"])
            candidate_root = _candidate_evidence_root(
                root, candidate, candidate_id=candidate_id
            )
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
                file_path = resolve_evidence_file(
                    candidate_root,
                    candidate.get(ref_field),
                    label=f"{candidate_id}.{ref_field}",
                )
                ref = file_path.relative_to(root).as_posix()
                if ref not in computed:
                    computed[ref] = compute_evidence_file_sha256(file_path)
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
    except ScaleSourcePoolEvidencePathError as exc:
        raise ScaleSourcePoolError(SOURCE_POOL_EVIDENCE_INVALID, [exc]) from exc
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

    if str(target_scale).strip() not in _MILESTONES:
        required_candidate_counts(target_scale)
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
        "waveCandidateCounts": [
            {
                "carrier": carrier,
                "minimumCandidateCount": sum(
                    str(candidate.get("carrier") or "") == carrier
                    for candidate in ordered
                ),
            }
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
