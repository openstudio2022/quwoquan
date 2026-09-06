#!/usr/bin/env python3
"""Permanent all-event promotion timing model and monotonic ratchet CLI."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CLASSIFICATIONS = (
    "success",
    "failure",
    "infra",
    "superseded",
    "unclassified",
    "incomplete",
)
CLASSIFICATION_SET = frozenset(CLASSIFICATIONS)
SAMPLE_SCHEMA = "quwoquan_ops.promotion_timing_sample"
AGGREGATE_SCHEMA = "quwoquan_ops.promotion_timing_aggregate"
RECOMMENDATION_SCHEMA = "quwoquan_ops.promotion_timing_recommendation"
POLICY_CONTRACT = "promotion-timing-ratchet-v1"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"
)
SAMPLE_KEYS = frozenset(
    {
        "schema",
        "observationId",
        "eventId",
        "repository",
        "workflowRunId",
        "runAttempt",
        "headSha",
        "baseSha",
        "firstAttemptAt",
        "promotionReadyAt",
        "observedAt",
        "mainReadbackAt",
        "durationSeconds",
        "classification",
        "timingComplete",
        "evidenceComplete",
        "policyDigest",
        "policyEpoch",
        "workflowDigest",
    }
)
POLICY_INTEGER_FIELDS = (
    "targetP95Seconds",
    "enforcementBudgetSeconds",
    "windowDays",
    "minimumEligibleEvents",
    "consecutiveQualifiedWindows",
    "quantilePercent",
    "roundingSeconds",
    "allowedUnclassifiedCancellations",
    "allowedDuplicateEvents",
    "allowedMissingEvidence",
)
IMMUTABLE_POLICY_FIELDS = (
    "schema_version",
    "contract_id",
    "metricId",
    "windowAnchorUtc",
    "windowDays",
    "quantile",
    "quantilePercent",
    "roundingSeconds",
    "denominator",
    "attemptClock",
)
EVENT_IDENTITY_FIELDS = (
    "eventId",
    "repository",
    "workflowRunId",
    "headSha",
    "baseSha",
    "firstAttemptAt",
    "promotionReadyAt",
    "policyDigest",
    "policyEpoch",
    "workflowDigest",
)


class PromotionTimingError(ValueError):
    """Raised when timing evidence could weaken or drift the permanent model."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise PromotionTimingError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PromotionTimingError(f"{field} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise PromotionTimingError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _forbidden_policy_key(key: object) -> bool:
    if not isinstance(key, str):
        return True
    normalized = re.sub(r"[^a-z]", "", key.lower())
    return normalized in {
        "stage",
        "stages",
        "phase",
        "phases",
        "mode",
        "maturity",
        "bypass",
        "exception",
        "successonly",
        "advisory",
        "hardphase",
    }


def _reject_policy_escapes(value: object, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if _forbidden_policy_key(key):
                raise PromotionTimingError(f"staged or bypass policy is forbidden at {path}.{key}")
            _reject_policy_escapes(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_policy_escapes(nested, path=f"{path}[{index}]")


def validate_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    if (
        policy.get("schema_version") != 1
        or policy.get("contract_id") != POLICY_CONTRACT
    ):
        raise PromotionTimingError("policy schema is invalid")
    _reject_policy_escapes(policy)
    for field in POLICY_INTEGER_FIELDS:
        value = policy.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PromotionTimingError(f"{field} must be a non-negative integer")
    if policy.get("metricId") != "dev1-main-promotion-ready-to-main-readback":
        raise PromotionTimingError("promotion metric identity drifted")
    if policy.get("attemptClock") != "first_attempt":
        raise PromotionTimingError("promotion timing must use the first attempt clock")
    if policy.get("denominator") != "all_eligible_promotion_events":
        raise PromotionTimingError("promotion denominator must contain every eligible event")
    if policy.get("quantile") != "nearest_rank" or policy["quantilePercent"] != 95:
        raise PromotionTimingError("promotion quantile must be nearest-rank p95")
    if policy["windowDays"] != 14:
        raise PromotionTimingError("promotion windows must be fixed non-overlapping 14 day windows")
    anchor = parse_time(policy.get("windowAnchorUtc"), "windowAnchorUtc")
    if anchor != datetime(1970, 1, 1, tzinfo=timezone.utc):
        raise PromotionTimingError("promotion UTC window anchor is immutable")
    if policy["targetP95Seconds"] != 300:
        raise PromotionTimingError("promotion p95 target is permanently fixed at 300 seconds")
    if policy["enforcementBudgetSeconds"] < policy["targetP95Seconds"]:
        raise PromotionTimingError("enforcement budget cannot be below the permanent target")
    if policy["minimumEligibleEvents"] < 30:
        raise PromotionTimingError("each qualified window requires at least 30 eligible events")
    if policy["consecutiveQualifiedWindows"] < 1:
        raise PromotionTimingError("consecutiveQualifiedWindows must be positive")
    if policy["roundingSeconds"] < 1:
        raise PromotionTimingError("roundingSeconds must be positive")
    completeness = policy.get("requiredTimingCompleteness")
    if isinstance(completeness, bool) or not isinstance(completeness, (float, int)):
        raise PromotionTimingError("requiredTimingCompleteness must be numeric")
    if float(completeness) != 1.0:
        raise PromotionTimingError("all eligible events require complete timing evidence")
    if tuple(policy.get("classifications") or ()) != CLASSIFICATIONS:
        raise PromotionTimingError("classification closed set or order drifted")
    monotonic = policy.get("monotonic")
    if not isinstance(monotonic, Mapping):
        raise PromotionTimingError("monotonic policy is required")
    expected_upper = {
        "enforcementBudgetSeconds",
        "targetP95Seconds",
        "allowedUnclassifiedCancellations",
        "allowedDuplicateEvents",
        "allowedMissingEvidence",
    }
    expected_lower = {
        "minimumEligibleEvents",
        "consecutiveQualifiedWindows",
        "requiredTimingCompleteness",
    }
    if set(monotonic.get("upperBoundFields") or ()) != expected_upper:
        raise PromotionTimingError("monotonic upper-bound fields drifted")
    if set(monotonic.get("lowerBoundFields") or ()) != expected_lower:
        raise PromotionTimingError("monotonic lower-bound fields drifted")
    if tuple(monotonic.get("requiredSetFields") or ()) != ("classifications",):
        raise PromotionTimingError("monotonic required-set fields drifted")
    governance = policy.get("governance")
    if not isinstance(governance, Mapping) or not all(
        isinstance(governance.get(field), str) and str(governance[field]).strip()
        for field in ("owner", "reason", "expires_when", "measure")
    ):
        raise PromotionTimingError("policy governance is incomplete")
    return dict(policy)


def policy_digest(policy: Mapping[str, Any]) -> str:
    canonical = validate_policy(policy)
    semantics = {key: canonical[key] for key in canonical if key != "governance"}
    return _digest(semantics)


def policy_epoch(policy_digest_value: str, workflow_digest: str) -> str:
    for field, value in (
        ("policyDigest", policy_digest_value),
        ("workflowDigest", workflow_digest),
    ):
        if SHA256_RE.fullmatch(value) is None:
            raise PromotionTimingError(f"{field} must be sha256")
    return _digest(
        {"policyDigest": policy_digest_value, "workflowDigest": workflow_digest}
    )


def _require_identity(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 512 or any(ord(char) < 32 for char in normalized):
        raise PromotionTimingError(f"{field} is invalid")
    return normalized


def make_sample(
    *,
    observation_id: str,
    event_id: str,
    repository: str,
    workflow_run_id: str,
    run_attempt: int,
    head_sha: str,
    base_sha: str,
    first_attempt_at: str,
    promotion_ready_at: str,
    observed_at: str,
    main_readback_at: str | None,
    classification: str,
    evidence_complete: bool,
    policy_digest: str,
    workflow_digest: str,
    policy_epoch_digest: str | None = None,
) -> dict[str, Any]:
    if classification not in CLASSIFICATION_SET:
        raise PromotionTimingError("classification is invalid")
    if isinstance(run_attempt, bool) or not isinstance(run_attempt, int) or run_attempt < 1:
        raise PromotionTimingError("runAttempt must be a positive integer")
    if REPOSITORY_RE.fullmatch(repository) is None:
        raise PromotionTimingError("repository must be an owner/name identity")
    if RUN_ID_RE.fullmatch(workflow_run_id) is None:
        raise PromotionTimingError("workflowRunId is invalid")
    if GIT_SHA_RE.fullmatch(head_sha) is None or GIT_SHA_RE.fullmatch(base_sha) is None:
        raise PromotionTimingError("headSha and baseSha must be 40 lowercase hex characters")
    if SHA256_RE.fullmatch(policy_digest) is None or SHA256_RE.fullmatch(workflow_digest) is None:
        raise PromotionTimingError("policyDigest and workflowDigest must be sha256")
    expected_epoch = policy_epoch(policy_digest, workflow_digest)
    if policy_epoch_digest is not None and policy_epoch_digest != expected_epoch:
        raise PromotionTimingError("policyEpoch does not bind policy and workflow digests")
    first = parse_time(first_attempt_at, "firstAttemptAt")
    ready = parse_time(promotion_ready_at, "promotionReadyAt")
    observed = parse_time(observed_at, "observedAt")
    readback = parse_time(main_readback_at, "mainReadbackAt") if main_readback_at else None
    if ready < first or observed < ready:
        raise PromotionTimingError("timing boundaries are not monotonic")
    if readback is not None and (readback < ready or readback > observed):
        raise PromotionTimingError("mainReadbackAt is outside the observed timing boundary")
    duration: int | None = None
    if readback is not None:
        raw_duration = (readback - ready).total_seconds()
        if not raw_duration.is_integer():
            raise PromotionTimingError("promotion duration must resolve to whole seconds")
        duration = int(raw_duration)
    if classification == "success" and (readback is None or not evidence_complete):
        raise PromotionTimingError("success requires complete main readback evidence")
    if classification == "incomplete" and readback is not None:
        raise PromotionTimingError("incomplete classification cannot contain main readback")
    timing_complete = readback is not None and bool(evidence_complete)
    return {
        "schema": SAMPLE_SCHEMA,
        "observationId": _require_identity(observation_id, "observationId"),
        "eventId": _require_identity(event_id, "eventId"),
        "repository": _require_identity(repository, "repository"),
        "workflowRunId": workflow_run_id,
        "runAttempt": run_attempt,
        "headSha": head_sha,
        "baseSha": base_sha,
        "firstAttemptAt": format_time(first),
        "promotionReadyAt": format_time(ready),
        "observedAt": format_time(observed),
        "mainReadbackAt": format_time(readback) if readback else None,
        "durationSeconds": duration,
        "classification": classification,
        "timingComplete": timing_complete,
        "evidenceComplete": bool(evidence_complete),
        "policyDigest": policy_digest,
        "policyEpoch": expected_epoch,
        "workflowDigest": workflow_digest,
    }


def validate_sample(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != SAMPLE_KEYS:
        raise PromotionTimingError("promotion timing sample has a non-canonical shape")
    canonical = make_sample(
        observation_id=str(value.get("observationId") or ""),
        event_id=str(value.get("eventId") or ""),
        repository=str(value.get("repository") or ""),
        workflow_run_id=str(value.get("workflowRunId") or ""),
        run_attempt=value.get("runAttempt"),  # type: ignore[arg-type]
        head_sha=str(value.get("headSha") or ""),
        base_sha=str(value.get("baseSha") or ""),
        first_attempt_at=str(value.get("firstAttemptAt") or ""),
        promotion_ready_at=str(value.get("promotionReadyAt") or ""),
        observed_at=str(value.get("observedAt") or ""),
        main_readback_at=(
            str(value["mainReadbackAt"])
            if value.get("mainReadbackAt") is not None
            else None
        ),
        classification=str(value.get("classification") or ""),
        evidence_complete=value.get("evidenceComplete") is True,
        policy_digest=str(value.get("policyDigest") or ""),
        workflow_digest=str(value.get("workflowDigest") or ""),
        policy_epoch_digest=str(value.get("policyEpoch") or ""),
    )
    if dict(value) != canonical:
        raise PromotionTimingError("promotion timing sample contains derived-field drift")
    return canonical


def nearest_rank_p95(values: Sequence[int]) -> int:
    if not values:
        raise PromotionTimingError("p95 requires samples")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise PromotionTimingError("p95 samples must be non-negative integers")
    ordered = sorted(values)
    return ordered[(95 * len(ordered) + 99) // 100 - 1]


def _window_anchor(policy: Mapping[str, Any]) -> datetime:
    return parse_time(policy["windowAnchorUtc"], "windowAnchorUtc")


def window_index(value: datetime, *, policy: Mapping[str, Any]) -> int:
    width = int(policy["windowDays"]) * 86400
    seconds = int((value.astimezone(timezone.utc) - _window_anchor(policy)).total_seconds())
    return seconds // width


def window_start(index: int, *, policy: Mapping[str, Any]) -> datetime:
    return _window_anchor(policy) + timedelta(days=int(policy["windowDays"]) * index)


def _effective_events(
    samples: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    duplicate_by_event: Counter[str] = Counter()
    observation_bytes: dict[str, bytes] = {}
    for raw in samples:
        sample = validate_sample(raw)
        observation_id = sample["observationId"]
        encoded = _canonical_bytes(sample)
        previous = observation_bytes.get(observation_id)
        if previous is not None:
            if previous != encoded:
                raise PromotionTimingError("observation identity has conflicting bytes")
            duplicate_by_event[sample["eventId"]] += 1
            continue
        observation_bytes[observation_id] = encoded
        grouped.setdefault(sample["eventId"], []).append(sample)
    effective: list[dict[str, Any]] = []
    for event_id, observations in grouped.items():
        first = observations[0]
        first_attempt = min(observations, key=lambda item: item["runAttempt"])
        if first_attempt["runAttempt"] != 1:
            raise PromotionTimingError(
                f"event {event_id!r} is missing the first workflow attempt"
            )
        for item in observations:
            for field in EVENT_IDENTITY_FIELDS:
                if item[field] != first[field]:
                    raise PromotionTimingError(
                        f"event {event_id!r} changed immutable first-attempt field {field}"
                    )
            if item["workflowRunId"] != first_attempt["workflowRunId"]:
                raise PromotionTimingError(
                    f"event {event_id!r} changed immutable workflow run identity"
                )
        attempts = Counter(item["runAttempt"] for item in observations)
        duplicate_by_event[event_id] += sum(
            count - 1 for count in attempts.values() if count > 1
        )
        terminal_by_attempt: dict[int, set[str]] = {}
        for item in observations:
            if item["classification"] != "incomplete":
                terminal_by_attempt.setdefault(item["runAttempt"], set()).add(
                    item["classification"]
                )
        if any(len(values) > 1 for values in terminal_by_attempt.values()):
            raise PromotionTimingError("one attempt has conflicting terminal classifications")
        successes = [item for item in observations if item["classification"] == "success"]
        if successes:
            selected = min(
                successes,
                key=lambda item: parse_time(item["mainReadbackAt"], "mainReadbackAt"),
            )
        else:
            selected = max(
                observations,
                key=lambda item: (
                    parse_time(item["observedAt"], "observedAt"), item["runAttempt"]
                ),
            )
        effective.append(dict(selected))
    effective.sort(
        key=lambda item: (
            parse_time(item["promotionReadyAt"], "promotionReadyAt"), item["eventId"]
        )
    )
    return effective, dict(duplicate_by_event)


def aggregate_windows(
    samples: Sequence[Mapping[str, Any]],
    policy: Mapping[str, Any],
    *,
    as_of: datetime | str | None = None,
) -> list[dict[str, Any]]:
    canonical_policy = validate_policy(policy)
    evaluated_at = (
        parse_time(as_of, "asOf")
        if isinstance(as_of, str)
        else (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    )
    effective, duplicate_by_event = _effective_events(samples)
    if not effective:
        return []
    grouped: dict[int, list[dict[str, Any]]] = {}
    duplicate_windows: Counter[int] = Counter()
    event_ids_by_head: dict[str, set[str]] = {}
    for sample in effective:
        event_ids_by_head.setdefault(sample["headSha"], set()).add(sample["eventId"])
    duplicate_head_events = {
        head_sha: len(event_ids)
        for head_sha, event_ids in event_ids_by_head.items()
        if len(event_ids) > 1
    }
    for sample in effective:
        index = window_index(
            parse_time(sample["promotionReadyAt"], "promotionReadyAt"),
            policy=canonical_policy,
        )
        grouped.setdefault(index, []).append(sample)
        duplicate_windows[index] += duplicate_by_event.get(sample["eventId"], 0)
        if sample["headSha"] in duplicate_head_events:
            duplicate_windows[index] += 1
    minimum_index = min(grouped)
    last_closed_index = window_index(
        evaluated_at - timedelta(microseconds=1), policy=canonical_policy
    )
    maximum_sample_index = max(grouped)
    maximum_index = max(maximum_sample_index, last_closed_index)
    result: list[dict[str, Any]] = []
    for index in range(minimum_index, maximum_index + 1):
        start = window_start(index, policy=canonical_policy)
        end = start + timedelta(days=canonical_policy["windowDays"])
        rows = grouped.get(index, [])
        complete = [
            row
            for row in rows
            if row["timingComplete"] is True
            and isinstance(row["durationSeconds"], int)
            and not isinstance(row["durationSeconds"], bool)
        ]
        counts = {name: 0 for name in CLASSIFICATIONS}
        for row in rows:
            counts[row["classification"]] += 1
        denominator = len(rows)
        completeness = len(complete) / denominator if denominator else 0.0
        missing = sum(
            row["evidenceComplete"] is not True or row["timingComplete"] is not True
            for row in rows
        )
        duplicates = duplicate_windows[index]
        epochs = {
            (row["policyDigest"], row["workflowDigest"], row["policyEpoch"])
            for row in rows
        }
        current_policy_digest = policy_digest(canonical_policy)
        policy_current = bool(rows) and all(
            row["policyDigest"] == current_policy_digest for row in rows
        )
        closed = end <= evaluated_at
        qualified = (
            closed
            and denominator >= canonical_policy["minimumEligibleEvents"]
            and completeness >= float(canonical_policy["requiredTimingCompleteness"])
            and counts["unclassified"]
            <= canonical_policy["allowedUnclassifiedCancellations"]
            and duplicates <= canonical_policy["allowedDuplicateEvents"]
            and missing <= canonical_policy["allowedMissingEvidence"]
            and sum(counts.values()) == denominator
            and len(epochs) == 1
            and policy_current
        )
        result.append(
            {
                "windowIndex": index,
                "windowStart": format_time(start),
                "windowEnd": format_time(end),
                "closed": closed,
                "denominator": denominator,
                "classificationCounts": counts,
                "completeSamples": len(complete),
                "timingCompleteness": completeness,
                "unclassified": counts["unclassified"],
                "missingEvidence": missing,
                "duplicateEvents": duplicates,
                "policyCurrent": policy_current,
                "policyEpoch": next(iter(epochs))[2] if len(epochs) == 1 else None,
                "p95Seconds": nearest_rank_p95(
                    [int(row["durationSeconds"]) for row in complete]
                )
                if complete
                else None,
                "qualified": qualified,
            }
        )
    return result


def next_budget(
    *, current_policy: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]
) -> int:
    policy = validate_policy(current_policy)
    closed = [item for item in windows if item.get("closed") is True]
    count = policy["consecutiveQualifiedWindows"]
    recent = closed[-count:]
    if len(recent) != count or not all(item.get("qualified") is True for item in recent):
        return policy["enforcementBudgetSeconds"]
    indexes = [int(item["windowIndex"]) for item in recent]
    if any(after != before + 1 for before, after in zip(indexes, indexes[1:])):
        return policy["enforcementBudgetSeconds"]
    epochs = {str(item.get("policyEpoch") or "") for item in recent}
    if len(epochs) != 1 or "" in epochs:
        return policy["enforcementBudgetSeconds"]
    p95_values = [item.get("p95Seconds") for item in recent]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in p95_values):
        return policy["enforcementBudgetSeconds"]
    rounding = policy["roundingSeconds"]
    observed = int(math.ceil(max(p95_values) / rounding) * rounding)  # type: ignore[arg-type]
    proposal = max(policy["targetP95Seconds"], observed)
    return min(policy["enforcementBudgetSeconds"], proposal)


def recommend_budget(
    *, current_policy: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    policy = validate_policy(current_policy)
    proposed = next_budget(current_policy=policy, windows=windows)
    return {
        "schema": RECOMMENDATION_SCHEMA,
        "policyDigest": policy_digest(policy),
        "currentBudgetSeconds": policy["enforcementBudgetSeconds"],
        "proposedBudgetSeconds": proposed,
        "targetP95Seconds": policy["targetP95Seconds"],
        "action": "lower" if proposed < policy["enforcementBudgetSeconds"] else "keep",
        "evaluatedWindowCount": len(windows),
    }


def verify_monotonic(previous: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    before = validate_policy(previous)
    after = validate_policy(candidate)
    for field in IMMUTABLE_POLICY_FIELDS:
        if after.get(field) != before.get(field):
            raise PromotionTimingError(f"immutable promotion timing field changed: {field}")
    before_governance = before["governance"]
    after_governance = after["governance"]
    if after_governance.get("measure") != before_governance.get("measure"):
        raise PromotionTimingError("permanent promotion timing measure drifted")
    if after.get("monotonic") != before.get("monotonic"):
        raise PromotionTimingError("monotonic field order changed")
    monotonic = before["monotonic"]
    for field in monotonic["upperBoundFields"]:
        if float(after[field]) > float(before[field]):
            raise PromotionTimingError(f"upper-bound field widened: {field}")
    for field in monotonic["lowerBoundFields"]:
        if float(after[field]) < float(before[field]):
            raise PromotionTimingError(f"lower-bound field weakened: {field}")
    for field in monotonic["requiredSetFields"]:
        if not set(after[field]).issuperset(before[field]):
            raise PromotionTimingError(f"required set shrank: {field}")


def _load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json" or path.name.endswith(".json"):
        return json.loads(text)
    import yaml

    return yaml.safe_load(text)


def _write_result(value: object, target: str) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if target:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


def _sample_rows(document: object) -> list[Mapping[str, Any]]:
    if isinstance(document, list):
        rows = document
    elif isinstance(document, Mapping) and isinstance(document.get("samples"), list):
        rows = document["samples"]
    else:
        raise PromotionTimingError("samples document must be an array or query result")
    if not all(isinstance(item, Mapping) for item in rows):
        raise PromotionTimingError("samples document contains a non-object row")
    return rows  # type: ignore[return-value]


def _add_output(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument("--write-json", required=required, default="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    policy_parser = subparsers.add_parser("policy-digest")
    policy_parser.add_argument("--policy", required=True, type=Path)
    _add_output(policy_parser, required=False)

    sample_parser = subparsers.add_parser("sample")
    for option in ("observation-id", "event-id", "repository", "workflow-run-id"):
        sample_parser.add_argument(f"--{option}", required=True)
    sample_parser.add_argument("--run-attempt", required=True, type=int)
    for option in (
        "head-sha", "base-sha", "first-attempt-at", "promotion-ready-at",
        "observed-at", "policy-digest", "workflow-digest",
    ):
        sample_parser.add_argument(f"--{option}", required=True)
    sample_parser.add_argument("--main-readback-at", default="")
    sample_parser.add_argument("--classification", required=True, choices=CLASSIFICATIONS)
    sample_parser.add_argument("--evidence-complete", required=True, choices=("true", "false"))
    _add_output(sample_parser, required=True)

    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--policy", required=True, type=Path)
    aggregate_parser.add_argument("--samples", required=True, type=Path)
    aggregate_parser.add_argument("--as-of", required=True)
    _add_output(aggregate_parser, required=True)

    recommend_parser = subparsers.add_parser("recommend")
    recommend_parser.add_argument("--policy", required=True, type=Path)
    recommend_parser.add_argument("--aggregate", required=True, type=Path)
    _add_output(recommend_parser, required=True)

    monotonic_parser = subparsers.add_parser("validate-monotonic")
    monotonic_parser.add_argument("--previous-policy", required=True, type=Path)
    monotonic_parser.add_argument("--candidate-policy", required=True, type=Path)
    _add_output(monotonic_parser, required=False)
    return parser


def _sample_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return make_sample(
        observation_id=args.observation_id,
        event_id=args.event_id,
        repository=args.repository,
        workflow_run_id=args.workflow_run_id,
        run_attempt=args.run_attempt,
        head_sha=args.head_sha,
        base_sha=args.base_sha,
        first_attempt_at=args.first_attempt_at,
        promotion_ready_at=args.promotion_ready_at,
        observed_at=args.observed_at,
        main_readback_at=args.main_readback_at or None,
        classification=args.classification,
        evidence_complete=args.evidence_complete == "true",
        policy_digest=args.policy_digest,
        workflow_digest=args.workflow_digest,
    )


def _aggregate_from_args(args: argparse.Namespace) -> dict[str, Any]:
    policy = _load_document(args.policy)
    return {
        "schema": AGGREGATE_SCHEMA,
        "policyDigest": policy_digest(policy),
        "asOf": format_time(parse_time(args.as_of, "asOf")),
        "windows": aggregate_windows(
            _sample_rows(_load_document(args.samples)), policy, as_of=args.as_of
        ),
    }


def _recommend_from_args(args: argparse.Namespace) -> dict[str, Any]:
    policy = _load_document(args.policy)
    aggregate = _load_document(args.aggregate)
    if not isinstance(aggregate, Mapping) or not isinstance(aggregate.get("windows"), list):
        raise PromotionTimingError("aggregate document is invalid")
    if aggregate.get("policyDigest") != policy_digest(policy):
        raise PromotionTimingError("aggregate policy digest does not match current policy")
    return recommend_budget(current_policy=policy, windows=aggregate["windows"])


def _monotonic_from_args(args: argparse.Namespace) -> dict[str, Any]:
    previous = _load_document(args.previous_policy)
    candidate = _load_document(args.candidate_policy)
    verify_monotonic(previous, candidate)
    return {
        "schema": "quwoquan_ops.promotion_timing_monotonic_validation",
        "previousPolicyDigest": policy_digest(previous),
        "candidatePolicyDigest": policy_digest(candidate),
        "valid": True,
    }


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.action == "policy-digest":
            result: object = {"policyDigest": policy_digest(_load_document(args.policy))}
        elif args.action == "sample":
            result = _sample_from_args(args)
        elif args.action == "aggregate":
            result = _aggregate_from_args(args)
        elif args.action == "recommend":
            result = _recommend_from_args(args)
        else:
            result = _monotonic_from_args(args)
        _write_result(result, args.write_json)
        return 0
    except (OSError, PromotionTimingError, ValueError, json.JSONDecodeError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
