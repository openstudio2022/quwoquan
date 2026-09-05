"""Deterministic calibration aggregation; advisory promotion remains human-owned."""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from quwoquan_ops.ci.impact_planner_core import canonical_digest


class CalibrationError(ValueError):
    """Raised when calibration samples cannot support an honest result."""


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return round(ordered[index], 3)


def aggregate_calibration(
    samples: Iterable[dict[str, Any]],
    *,
    policy: dict[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    values = list(samples)
    identities: set[tuple[int, str]] = set()
    durations: list[float] = []
    finding_counts: Counter[str] = Counter()
    terminal_counts: Counter[str] = Counter()
    reviewed = false_positives = unknown_advisories = 0
    for sample in values:
        if set(sample) != {"pullRequest", "durationSeconds", "report", "findingReviews"}:
            raise CalibrationError("calibration sample 字段不闭合")
        pull_request = sample["pullRequest"]
        duration = sample["durationSeconds"]
        report = sample["report"]
        reviews = sample["findingReviews"]
        if isinstance(pull_request, bool) or not isinstance(pull_request, int) or pull_request <= 0:
            raise CalibrationError("pullRequest 必须为正整数")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
            raise CalibrationError("durationSeconds 必须为非负数")
        if not isinstance(report, dict) or report.get("schema") != "quwoquan.code-health-delta.v1":
            raise CalibrationError("sample report schema 非法")
        if report.get("candidateSource") != "commit":
            raise CalibrationError("calibration 只接受 clean commit candidate")
        head = report.get("headSha")
        if not isinstance(head, str):
            raise CalibrationError("sample headSha 缺失")
        identity = (pull_request, head)
        if identity in identities:
            raise CalibrationError("calibration sample identity 重复")
        identities.add(identity)
        if not isinstance(reviews, list):
            raise CalibrationError("findingReviews 必须为 list")
        review_map: dict[tuple[str, str], str] = {}
        for review in reviews:
            if not isinstance(review, dict) or set(review) != {"code", "path", "verdict"}:
                raise CalibrationError("findingReview 字段不闭合")
            verdict = review["verdict"]
            if verdict not in {"confirmed", "false-positive"}:
                raise CalibrationError("findingReview.verdict 非法")
            key = (str(review["code"]), str(review["path"]))
            if key in review_map:
                raise CalibrationError("findingReview identity 重复")
            review_map[key] = verdict
        durations.append(float(duration))
        terminal_counts[str(report.get("terminal"))] += 1
        for finding in report.get("findings") or []:
            code = str(finding.get("code"))
            path = str(finding.get("path"))
            finding_counts[code] += 1
            verdict = review_map.get((code, path))
            if verdict:
                reviewed += 1
                false_positives += verdict == "false-positive"
            elif finding.get("terminal") == "PR_WARN":
                unknown_advisories += 1
    calibration = policy["rollout"]["calibration"]
    started_at = datetime.fromisoformat(calibration["started_at"])
    if started_at.tzinfo is None or observed_at.tzinfo is None:
        raise CalibrationError("calibration chronology 必须带时区")
    elapsed_days = max(0, (observed_at - started_at).days)
    sample_gate = elapsed_days >= calibration["minimum_days"] or len(values) >= calibration["minimum_pull_requests"]
    false_positive_rate = None if reviewed == 0 else round(false_positives / reviewed, 4)
    false_positive_gate = false_positive_rate is not None and false_positive_rate <= calibration["maximum_confirmed_false_positive_rate"]
    p95 = _percentile(durations, 0.95)
    performance_gate = p95 is not None and p95 <= policy["performance"]["ci_p95_seconds"]
    eligible = sample_gate and false_positive_gate and performance_gate and unknown_advisories == 0
    digest_payload = {
        "policyId": policy["policy_id"],
        "samples": [
            {
                "pullRequest": sample["pullRequest"],
                "headSha": sample["report"]["headSha"],
                "fingerprint": sample["report"]["evidenceFingerprint"]["digest"],
                "durationSeconds": sample["durationSeconds"],
                "findingReviews": sample["findingReviews"],
            }
            for sample in values
        ],
    }
    return {
        "schema": "quwoquan.code-health-calibration.v1",
        "policyId": policy["policy_id"],
        "sampleCount": len(values),
        "elapsedDays": elapsed_days,
        "terminalCounts": dict(sorted(terminal_counts.items())),
        "findingCounts": dict(sorted(finding_counts.items())),
        "performance": {"p95Seconds": p95, "targetP95Seconds": policy["performance"]["ci_p95_seconds"]},
        "review": {
            "reviewedFindingCount": reviewed,
            "unreviewedAdvisoryCount": unknown_advisories,
            "confirmedFalsePositiveCount": false_positives,
            "confirmedFalsePositiveRate": false_positive_rate,
            "maximumRate": calibration["maximum_confirmed_false_positive_rate"],
        },
        "promotion": {
            "sampleGate": sample_gate,
            "performanceGate": performance_gate,
            "falsePositiveGate": false_positive_gate,
            "eligibleForHumanPolicyRevision": eligible,
            "automaticPromotion": False,
            "recommendation": "eligible-for-human-policy-revision" if eligible else "keep-advisory",
        },
        "sampleSetDigest": canonical_digest(digest_payload),
        "observedAt": observed_at.isoformat(timespec="seconds"),
    }
