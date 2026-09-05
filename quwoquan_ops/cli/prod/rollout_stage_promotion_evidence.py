#!/usr/bin/env python3
"""Validate protected, candidate-bound rollout-stage promotion observations."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "prod-rollout-stage-observation"
RECEIPT_SCHEMA = "prod-rollout-stage-promotion-evidence"
AUTHORITY = "protected-prod-runner"
SOURCE_AUTHORITY = "prod-observability-plane"
STAGES = ("canary", "5", "20", "50", "100")
PLATFORMS = ("android", "ios", "web")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
STAGE_THRESHOLDS = {
    "canary": {
        "durationSeconds": 0,
        "candidateRequests": 0,
        "uniqueInstallations": 6,
        "perPlatformInstallations": 2,
        "syntheticRequests": 120,
    },
    "5": {
        "durationSeconds": 30 * 60,
        "candidateRequests": 1000,
        "uniqueInstallations": 50,
        "perPlatformInstallations": 10,
        "syntheticRequests": 0,
    },
    "20": {
        "durationSeconds": 2 * 60 * 60,
        "candidateRequests": 5000,
        "uniqueInstallations": 200,
        "perPlatformInstallations": 30,
        "syntheticRequests": 0,
    },
    "50": {
        "durationSeconds": 24 * 60 * 60,
        "candidateRequests": 20000,
        "uniqueInstallations": 1000,
        "perPlatformInstallations": 100,
        "syntheticRequests": 0,
    },
    "100": {
        "durationSeconds": 0,
        "candidateRequests": 0,
        "uniqueInstallations": 3,
        "perPlatformInstallations": 1,
        "syntheticRequests": 0,
    },
}


class PromotionEvidenceError(RuntimeError):
    pass


def canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_protected_observation(path: Path, *, trusted_root: Path) -> dict[str, Any]:
    if not trusted_root.is_absolute() or not path.is_absolute():
        raise PromotionEvidenceError("promotion evidence paths must be absolute")
    if trusted_root.is_symlink() or not trusted_root.is_dir():
        raise PromotionEvidenceError("protected promotion evidence root is unavailable")
    resolved_root = trusted_root.resolve(strict=True)
    if path.is_symlink() or not path.is_file():
        raise PromotionEvidenceError("promotion evidence file is unavailable or unsafe")
    resolved_path = path.resolve(strict=True)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise PromotionEvidenceError(
            "promotion evidence file is outside the protected runner root"
        ) from error
    for candidate, label in (
        (resolved_root, "root"),
        (resolved_path, "file"),
    ):
        descriptor = candidate.stat()
        if descriptor.st_uid != os.getuid():
            raise PromotionEvidenceError(
                f"protected promotion evidence {label} has an unexpected owner"
            )
        if descriptor.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise PromotionEvidenceError(
                f"protected promotion evidence {label} is group/world writable"
            )
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PromotionEvidenceError("promotion evidence is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise PromotionEvidenceError("promotion evidence must be an object")
    return payload


def validate_observation(
    value: object,
    *,
    candidate_id: str,
    artifact_digest: str,
    campaign_id: str,
    routing_policy_digest: str,
    stage: str,
    stage_policy: Mapping[str, Any],
    actual_synthetic_requests: int | None,
) -> dict[str, Any]:
    expected_fields = {
        "schema",
        "authority",
        "releaseCompositionId",
        "artifactDigest",
        "campaignId",
        "routingPolicyDigest",
        "stage",
        "observedFrom",
        "observedUntil",
        "candidateRequestCount",
        "uniqueCandidateInstallations",
        "platforms",
        "audiences",
        "supportedAppCoverage",
        "source",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise PromotionEvidenceError("promotion evidence shape is not canonical")
    if (
        value.get("schema") != SCHEMA
        or value.get("authority") != AUTHORITY
        or value.get("releaseCompositionId") != candidate_id
        or value.get("artifactDigest") != artifact_digest
        or value.get("campaignId") != campaign_id
        or value.get("routingPolicyDigest") != routing_policy_digest
        or value.get("stage") != stage
    ):
        raise PromotionEvidenceError(
            "promotion evidence is not bound to candidate, artifact, campaign, policy and stage"
        )
    if stage not in STAGE_THRESHOLDS:
        raise PromotionEvidenceError("promotion evidence stage is invalid")
    observed_from = _timestamp(value["observedFrom"], "observedFrom")
    observed_until = _timestamp(value["observedUntil"], "observedUntil")
    if observed_until < observed_from:
        raise PromotionEvidenceError("promotion observation interval is invalid")
    duration_seconds = int((observed_until - observed_from).total_seconds())
    thresholds = STAGE_THRESHOLDS[stage]
    if duration_seconds < thresholds["durationSeconds"]:
        raise PromotionEvidenceError(
            f"stage {stage} observation duration is below {thresholds['durationSeconds']} seconds"
        )

    request_count = _non_negative_int(
        value["candidateRequestCount"], "candidateRequestCount"
    )
    installation_count = _non_negative_int(
        value["uniqueCandidateInstallations"],
        "uniqueCandidateInstallations",
    )
    if request_count < thresholds["candidateRequests"]:
        raise PromotionEvidenceError(
            f"stage {stage} candidate requests are below {thresholds['candidateRequests']}"
        )
    if installation_count < thresholds["uniqueInstallations"]:
        raise PromotionEvidenceError(
            f"stage {stage} unique installations are below {thresholds['uniqueInstallations']}"
        )

    expected_platforms = _selected_values(stage_policy.get("platforms"), "platforms")
    if stage in {"canary", "100"}:
        expected_platforms = set(PLATFORMS)
    platforms = _validate_platforms(
        value["platforms"],
        expected_platforms=expected_platforms,
        minimum_installations=thresholds["perPlatformInstallations"],
    )
    if sum(item["candidateRequestCount"] for item in platforms.values()) != request_count:
        raise PromotionEvidenceError("platform request totals do not equal candidateRequestCount")
    if (
        sum(item["uniqueCandidateInstallations"] for item in platforms.values())
        != installation_count
    ):
        raise PromotionEvidenceError(
            "platform installation totals do not equal uniqueCandidateInstallations"
        )

    audiences = value["audiences"]
    if not isinstance(audiences, dict) or set(audiences) != {"regions", "carriers"}:
        raise PromotionEvidenceError("promotion audience observations are incomplete")
    validated_audiences = {
        dimension: _validate_audience(
            audiences[dimension],
            selector=stage_policy.get(dimension),
            label=dimension,
        )
        for dimension in ("regions", "carriers")
    }

    app_coverage = value["supportedAppCoverage"]
    expected_app_mode = str((stage_policy.get("appVersions") or {}).get("mode") or "")
    if (
        not isinstance(app_coverage, dict)
        or set(app_coverage) != {"mode", "complete"}
        or app_coverage.get("mode") != expected_app_mode
        or not isinstance(app_coverage.get("complete"), bool)
        or (stage == "100" and app_coverage.get("complete") is not True)
    ):
        raise PromotionEvidenceError("supported App coverage evidence is invalid")

    source = _validate_source(value["source"], observed_until=observed_until)
    synthetic_requests = 0 if actual_synthetic_requests is None else _non_negative_int(
        actual_synthetic_requests,
        "actualSyntheticRequests",
    )
    if (
        actual_synthetic_requests is not None
        and synthetic_requests < thresholds["syntheticRequests"]
    ):
        raise PromotionEvidenceError(
            f"stage {stage} synthetic requests are below {thresholds['syntheticRequests']}"
        )
    projection = {
        "schema": RECEIPT_SCHEMA,
        "authority": AUTHORITY,
        "releaseCompositionId": candidate_id,
        "artifactDigest": artifact_digest,
        "campaignId": campaign_id,
        "routingPolicyDigest": routing_policy_digest,
        "stage": stage,
        "observedFrom": value["observedFrom"],
        "observedUntil": value["observedUntil"],
        "durationSeconds": duration_seconds,
        "syntheticRequestCount": synthetic_requests,
        "candidateRequestCount": request_count,
        "uniqueCandidateInstallations": installation_count,
        "platforms": platforms,
        "audiences": validated_audiences,
        "supportedAppCoverage": dict(app_coverage),
        "source": source,
    }
    projection["evidenceDigest"] = canonical_digest(projection)
    return projection


def validate_receipt_evidence(
    value: object,
    *,
    candidate_id: object,
    artifact_digest: object,
    stage: object,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("promotionEvidence must be an object")
    expected_fields = {
        "schema",
        "authority",
        "releaseCompositionId",
        "artifactDigest",
        "campaignId",
        "routingPolicyDigest",
        "stage",
        "observedFrom",
        "observedUntil",
        "durationSeconds",
        "syntheticRequestCount",
        "candidateRequestCount",
        "uniqueCandidateInstallations",
        "platforms",
        "audiences",
        "supportedAppCoverage",
        "source",
        "evidenceDigest",
    }
    if set(value) != expected_fields:
        raise ValueError("promotionEvidence shape is not canonical")
    if (
        value.get("schema") != RECEIPT_SCHEMA
        or value.get("authority") != AUTHORITY
        or value.get("releaseCompositionId") != candidate_id
        or value.get("artifactDigest") != artifact_digest
        or value.get("stage") != stage
        or DIGEST_RE.fullmatch(str(value.get("routingPolicyDigest") or "")) is None
        or DIGEST_RE.fullmatch(str(value.get("evidenceDigest") or "")) is None
    ):
        raise ValueError("promotionEvidence binding is invalid")
    unsigned = dict(value)
    digest = unsigned.pop("evidenceDigest")
    if canonical_digest(unsigned) != digest:
        raise ValueError("promotionEvidence digest is invalid")
    _timestamp(value["observedFrom"], "promotionEvidence.observedFrom")
    _timestamp(value["observedUntil"], "promotionEvidence.observedUntil")
    for field in (
        "durationSeconds",
        "syntheticRequestCount",
        "candidateRequestCount",
        "uniqueCandidateInstallations",
    ):
        _non_negative_int(value[field], f"promotionEvidence.{field}")
    return dict(value)


def _validate_platforms(
    value: object,
    *,
    expected_platforms: set[str],
    minimum_installations: int,
) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict) or set(value) != expected_platforms:
        raise PromotionEvidenceError(
            "platform evidence must exactly match the selected rollout platforms"
        )
    result: dict[str, dict[str, int]] = {}
    for platform in sorted(expected_platforms):
        item = value[platform]
        if not isinstance(item, dict) or set(item) != {
            "candidateRequestCount",
            "uniqueCandidateInstallations",
        }:
            raise PromotionEvidenceError(f"platform {platform} evidence is invalid")
        requests = _non_negative_int(
            item["candidateRequestCount"],
            f"platforms.{platform}.candidateRequestCount",
        )
        installations = _non_negative_int(
            item["uniqueCandidateInstallations"],
            f"platforms.{platform}.uniqueCandidateInstallations",
        )
        if installations < minimum_installations:
            raise PromotionEvidenceError(
                f"platform {platform} installations are below {minimum_installations}"
            )
        result[platform] = {
            "candidateRequestCount": requests,
            "uniqueCandidateInstallations": installations,
        }
    return result


def _validate_audience(
    value: object,
    *,
    selector: object,
    label: str,
) -> dict[str, Any]:
    if not isinstance(selector, dict):
        raise PromotionEvidenceError(f"rollout {label} selector is missing")
    mode = str(selector.get("mode") or "")
    selected = {str(item) for item in (selector.get("values") or [])}
    if not isinstance(value, dict) or set(value) != {"mode", "observations"}:
        raise PromotionEvidenceError(f"{label} observations are invalid")
    if value.get("mode") != mode or not isinstance(value.get("observations"), list):
        raise PromotionEvidenceError(f"{label} observations do not match rollout mode")
    observations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value["observations"]:
        if not isinstance(raw, dict) or set(raw) != {
            "value",
            "top",
            "candidateRequestCount",
            "uniqueCandidateInstallations",
        }:
            raise PromotionEvidenceError(f"{label} observation shape is invalid")
        segment = str(raw.get("value") or "")
        if not segment or segment in seen or not isinstance(raw.get("top"), bool):
            raise PromotionEvidenceError(f"{label} observation identity is invalid")
        seen.add(segment)
        observations.append(
            {
                "value": segment,
                "top": raw["top"],
                "candidateRequestCount": _non_negative_int(
                    raw["candidateRequestCount"],
                    f"{label}.{segment}.candidateRequestCount",
                ),
                "uniqueCandidateInstallations": _non_negative_int(
                    raw["uniqueCandidateInstallations"],
                    f"{label}.{segment}.uniqueCandidateInstallations",
                ),
            }
        )
    by_value = {item["value"]: item for item in observations}
    if mode == "include":
        if not selected or seen != selected:
            raise PromotionEvidenceError(f"directed {label} evidence is incomplete")
        for segment in selected:
            item = by_value[segment]
            if (
                item["uniqueCandidateInstallations"] < 10
                or item["candidateRequestCount"] < 100
            ):
                raise PromotionEvidenceError(
                    f"directed {label} {segment} lacks 10 installations and 100 requests"
                )
    elif mode == "all":
        if "unknown" not in by_value or not any(
            item["top"] and item["value"] != "unknown" for item in observations
        ):
            raise PromotionEvidenceError(
                f"all-mode {label} evidence must observe top segments and unknown"
            )
    else:
        raise PromotionEvidenceError(f"rollout {label} mode is invalid")
    return {"mode": mode, "observations": observations}


def _validate_source(value: object, *, observed_until: dt.datetime) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "authority",
        "queryDigest",
        "receiptDigest",
        "generatedAt",
    }:
        raise PromotionEvidenceError("promotion evidence source is invalid")
    if value.get("authority") != SOURCE_AUTHORITY:
        raise PromotionEvidenceError("promotion evidence source authority is invalid")
    for field in ("queryDigest", "receiptDigest"):
        if DIGEST_RE.fullmatch(str(value.get(field) or "")) is None:
            raise PromotionEvidenceError(f"promotion evidence source {field} is invalid")
    generated_at = _timestamp(value["generatedAt"], "source.generatedAt")
    if generated_at < observed_until:
        raise PromotionEvidenceError("promotion evidence was generated before observation end")
    if generated_at > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        raise PromotionEvidenceError("promotion evidence source is future-dated")
    return dict(value)


def _selected_values(value: object, label: str) -> set[str]:
    if not isinstance(value, dict) or value.get("mode") != "include":
        raise PromotionEvidenceError(f"rollout {label} selector must use include mode")
    selected = {str(item) for item in (value.get("values") or [])}
    if not selected or not selected.issubset(PLATFORMS):
        raise PromotionEvidenceError(f"rollout {label} selector is invalid")
    return selected


def _timestamp(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise PromotionEvidenceError(f"{field} must be a timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PromotionEvidenceError(f"{field} must be a timestamp") from error
    if parsed.tzinfo is None:
        raise PromotionEvidenceError(f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PromotionEvidenceError(f"{field} must be a non-negative integer")
    return value
