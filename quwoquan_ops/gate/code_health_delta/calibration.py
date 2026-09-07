"""Deterministic calibration aggregation; advisory promotion remains human-owned.

升格资格按 finding code 抽样判定：每个 advisory code 至少有 `minimum_reviewed_per_code` 条人工
评审且 confirmed false-positive 不超过上限，才对该 code 给出 `eligible`；不要求评审全部
advisory（那是不可达的门），也不存在自动升格。
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from quwoquan_ops.ci.impact_planner_core import canonical_digest

from .engine import REPORT_SCHEMA

_SAMPLE_FIELDS = frozenset({"pullRequest", "durationSeconds", "report", "findingReviews"})
_REVIEW_FIELDS = frozenset({"code", "path", "verdict"})
_VERDICTS = frozenset({"confirmed", "false-positive"})


class CalibrationError(ValueError):
    """Raised when calibration samples cannot support an honest result."""


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return round(ordered[index], 3)


def _review_verdicts(reviews: Any) -> dict[tuple[str, str], str]:
    if not isinstance(reviews, list):
        raise CalibrationError("findingReviews 必须为 list")
    verdicts: dict[tuple[str, str], str] = {}
    for review in reviews:
        if not isinstance(review, dict) or set(review) != _REVIEW_FIELDS:
            raise CalibrationError("findingReview 字段不闭合")
        if review["verdict"] not in _VERDICTS:
            raise CalibrationError("findingReview.verdict 非法")
        key = (str(review["code"]), str(review["path"]))
        if key in verdicts:
            raise CalibrationError("findingReview identity 重复")
        verdicts[key] = review["verdict"]
    return verdicts


def _validate_sample(sample: dict[str, Any]) -> tuple[int, float, dict[str, Any], dict[tuple[str, str], str]]:
    if set(sample) != _SAMPLE_FIELDS:
        raise CalibrationError("calibration sample 字段不闭合")
    pull_request = sample["pullRequest"]
    duration = sample["durationSeconds"]
    report = sample["report"]
    if isinstance(pull_request, bool) or not isinstance(pull_request, int) or pull_request <= 0:
        raise CalibrationError("pullRequest 必须为正整数")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
        raise CalibrationError("durationSeconds 必须为非负数")
    if not isinstance(report, dict) or report.get("schema") != REPORT_SCHEMA:
        raise CalibrationError("sample report schema 非法")
    if report.get("candidateSource") != "commit":
        raise CalibrationError("calibration 只接受 clean commit candidate")
    if not isinstance(report.get("headSha"), str):
        raise CalibrationError("sample headSha 缺失")
    return pull_request, float(duration), report, _review_verdicts(sample["findingReviews"])


class _CodeTally:
    """Per-code review counts; terminal records whether the code is advisory or blocking."""

    def __init__(self) -> None:
        self.total = 0
        self.reviewed = 0
        self.false_positives = 0
        self.terminals: set[str] = set()

    def record(self, terminal: str, verdict: str | None) -> None:
        self.total += 1
        self.terminals.add(terminal)
        if verdict is not None:
            self.reviewed += 1
            self.false_positives += verdict == "false-positive"

    @property
    def false_positive_rate(self) -> float | None:
        return None if self.reviewed == 0 else round(self.false_positives / self.reviewed, 4)


def _tally(values: list[dict[str, Any]]) -> tuple[list[float], Counter[str], dict[str, _CodeTally]]:
    identities: set[tuple[int, str]] = set()
    durations: list[float] = []
    terminal_counts: Counter[str] = Counter()
    per_code: dict[str, _CodeTally] = {}
    for sample in values:
        pull_request, duration, report, verdicts = _validate_sample(sample)
        identity = (pull_request, report["headSha"])
        if identity in identities:
            raise CalibrationError("calibration sample identity 重复")
        identities.add(identity)
        durations.append(duration)
        terminal_counts[str(report.get("terminal"))] += 1
        for finding in report.get("findings") or []:
            code = str(finding.get("code"))
            tally = per_code.setdefault(code, _CodeTally())
            tally.record(str(finding.get("terminal")), verdicts.get((code, str(finding.get("path")))))
    return durations, terminal_counts, per_code


def _per_code_promotion(per_code: dict[str, _CodeTally], calibration: dict[str, Any]) -> dict[str, dict[str, Any]]:
    minimum = calibration["minimum_reviewed_per_code"]
    maximum_rate = calibration["maximum_confirmed_false_positive_rate"]
    result: dict[str, dict[str, Any]] = {}
    for code in sorted(per_code):
        tally = per_code[code]
        rate = tally.false_positive_rate
        advisory = "PR_WARN" in tally.terminals
        result[code] = {
            "advisory": advisory,
            "total": tally.total,
            "reviewed": tally.reviewed,
            "minimumReviewed": minimum,
            "falsePositiveRate": rate,
            "eligible": advisory and tally.reviewed >= minimum and rate is not None and rate <= maximum_rate,
        }
    return result


def _elapsed_days(calibration: dict[str, Any], observed_at: datetime) -> int:
    started_at = datetime.fromisoformat(calibration["started_at"])
    if started_at.tzinfo is None or observed_at.tzinfo is None:
        raise CalibrationError("calibration chronology 必须带时区")
    return max(0, (observed_at - started_at).days)


def _review_summary(per_code: dict[str, _CodeTally], calibration: dict[str, Any]) -> dict[str, Any]:
    reviewed = sum(tally.reviewed for tally in per_code.values())
    false_positives = sum(tally.false_positives for tally in per_code.values())
    rate = None if reviewed == 0 else round(false_positives / reviewed, 4)
    return {
        "reviewedFindingCount": reviewed,
        "unreviewedAdvisoryCount": sum(
            tally.total - tally.reviewed for tally in per_code.values() if "PR_WARN" in tally.terminals
        ),
        "confirmedFalsePositiveCount": false_positives,
        "confirmedFalsePositiveRate": rate,
        "maximumRate": calibration["maximum_confirmed_false_positive_rate"],
        "minimumReviewedPerCode": calibration["minimum_reviewed_per_code"],
    }


def aggregate_calibration(
    samples: Iterable[dict[str, Any]],
    *,
    policy: dict[str, Any],
    observed_at: datetime,
) -> dict[str, Any]:
    values = list(samples)
    durations, terminal_counts, per_code = _tally(values)
    calibration = policy["rollout"]["calibration"]
    elapsed_days = _elapsed_days(calibration, observed_at)
    sample_gate = elapsed_days >= calibration["minimum_days"] or len(values) >= calibration["minimum_pull_requests"]
    review = _review_summary(per_code, calibration)
    false_positive_gate = review["confirmedFalsePositiveRate"] is not None and review["confirmedFalsePositiveRate"] <= review["maximumRate"]
    p95 = _percentile(durations, 0.95)
    performance_gate = p95 is not None and p95 <= policy["performance"]["ci_p95_seconds"]
    per_code_promotion = _per_code_promotion(per_code, calibration)
    eligible_codes = sorted(code for code, item in per_code_promotion.items() if item["eligible"])
    eligible = sample_gate and performance_gate and bool(eligible_codes)
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
        "findingCounts": {code: per_code[code].total for code in sorted(per_code)},
        "performance": {"p95Seconds": p95, "targetP95Seconds": policy["performance"]["ci_p95_seconds"]},
        "review": review,
        "promotion": {
            "sampleGate": sample_gate,
            "performanceGate": performance_gate,
            "falsePositiveGate": false_positive_gate,
            "perCode": per_code_promotion,
            "eligibleCodes": eligible_codes,
            "eligibleForHumanPolicyRevision": eligible,
            "automaticPromotion": False,
            "recommendation": "eligible-for-human-policy-revision" if eligible else "keep-advisory",
        },
        "sampleSetDigest": canonical_digest(digest_payload),
        "observedAt": observed_at.isoformat(timespec="seconds"),
    }
