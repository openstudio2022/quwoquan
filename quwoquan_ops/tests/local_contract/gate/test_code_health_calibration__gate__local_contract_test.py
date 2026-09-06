"""Code-health calibration remains evidence-bound and human-promoted.

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-002.t3
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from quwoquan_ops.gate.code_health_delta.calibration import CalibrationError, aggregate_calibration
from quwoquan_ops.gate.code_health_delta.engine import REPORT_SCHEMA
from quwoquan_ops.gate.code_health_delta.policy import load_policy

ROOT = Path(__file__).resolve().parents[4]
POLICY = load_policy(ROOT / "quwoquan_ops/policies/code_health_policy.yaml")
OBSERVED = datetime(2026, 9, 6, tzinfo=timezone.utc)
COMPLEXITY = "CODE_HEALTH.COMPLEXITY_ADVISORY"
DUPLICATION = "CODE_HEALTH.DUPLICATION_ADVISORY"


def _sample(number: int, *, reviewed: bool, codes: tuple[str, ...] = (COMPLEXITY,), verdict: str = "confirmed") -> dict:
    findings = [{"code": code, "path": f"quwoquan_ops/ci/{number}.py", "terminal": "PR_WARN"} for code in codes]
    report = {
        "schema": REPORT_SCHEMA, "candidateSource": "commit",
        "headSha": f"{number:040x}", "terminal": "PR_WARN", "findings": findings,
        "evidenceFingerprint": {"digest": "sha256:" + f"{number:064x}"},
    }
    reviews = [{"code": item["code"], "path": item["path"], "verdict": verdict} for item in findings] if reviewed else []
    return {"pullRequest": number, "durationSeconds": 12.0, "report": report, "findingReviews": reviews}


def test_twenty_unreviewed_prs_never_auto_promote() -> None:
    result = aggregate_calibration([_sample(number, reviewed=False) for number in range(1, 21)], policy=POLICY, observed_at=OBSERVED)
    assert result["promotion"]["sampleGate"] is True
    assert result["promotion"]["performanceGate"] is True
    assert result["promotion"]["falsePositiveGate"] is False
    assert result["promotion"]["eligibleForHumanPolicyRevision"] is False
    assert result["promotion"]["automaticPromotion"] is False
    assert result["promotion"]["recommendation"] == "keep-advisory"
    assert result["promotion"]["perCode"][COMPLEXITY]["eligible"] is False
    assert result["review"]["unreviewedAdvisoryCount"] == 20


def test_reviewed_low_false_positive_fast_sample_only_recommends_human_revision() -> None:
    samples = [_sample(number, reviewed=True) for number in range(1, 21)]
    result = aggregate_calibration(samples, policy=POLICY, observed_at=OBSERVED)
    assert result["promotion"]["eligibleForHumanPolicyRevision"] is True
    assert result["promotion"]["eligibleCodes"] == [COMPLEXITY]
    assert result["promotion"]["automaticPromotion"] is False
    assert result["review"]["confirmedFalsePositiveRate"] == 0.0

    slow = deepcopy(samples)
    for sample in slow[-2:]:
        sample["durationSeconds"] = 181.0
    result = aggregate_calibration(slow, policy=POLICY, observed_at=OBSERVED)
    assert result["promotion"]["performanceGate"] is False
    assert result["promotion"]["eligibleForHumanPolicyRevision"] is False


def test_eligibility_is_sampled_per_code_not_all_advisories() -> None:
    minimum = POLICY["rollout"]["calibration"]["minimum_reviewed_per_code"]
    # 复杂度 code 抽样评审满 20 条；重复 code 一条都没评审：前者达标，后者不达标，整体仍可进入人工修订。
    samples = [_sample(number, reviewed=True) for number in range(1, minimum + 1)]
    samples += [_sample(number, reviewed=False, codes=(DUPLICATION,)) for number in range(minimum + 1, minimum + 41)]
    result = aggregate_calibration(samples, policy=POLICY, observed_at=OBSERVED)
    per_code = result["promotion"]["perCode"]
    assert per_code[COMPLEXITY] == {
        "advisory": True, "total": minimum, "reviewed": minimum, "minimumReviewed": minimum,
        "falsePositiveRate": 0.0, "eligible": True,
    }
    assert per_code[DUPLICATION]["eligible"] is False and per_code[DUPLICATION]["reviewed"] == 0
    assert result["promotion"]["eligibleCodes"] == [COMPLEXITY]
    assert result["promotion"]["eligibleForHumanPolicyRevision"] is True
    assert result["review"]["unreviewedAdvisoryCount"] == 40

    # 样本不足最小评审数的 code 不给资格，即使零误报。
    short = [_sample(number, reviewed=True) for number in range(1, minimum)]
    short += [_sample(number, reviewed=False) for number in range(minimum, 21)]
    result = aggregate_calibration(short, policy=POLICY, observed_at=OBSERVED)
    assert result["promotion"]["perCode"][COMPLEXITY]["reviewed"] == minimum - 1
    assert result["promotion"]["eligibleForHumanPolicyRevision"] is False

    # 误报率超过上限的 code 不给资格。
    noisy = [_sample(number, reviewed=True, verdict="false-positive" if number <= 3 else "confirmed") for number in range(1, 21)]
    result = aggregate_calibration(noisy, policy=POLICY, observed_at=OBSERVED)
    assert result["promotion"]["perCode"][COMPLEXITY]["falsePositiveRate"] == 0.15
    assert result["promotion"]["eligibleForHumanPolicyRevision"] is False


def test_sample_contract_is_closed() -> None:
    broken = _sample(1, reviewed=True)
    broken["findingReviews"][0]["verdict"] = "maybe"
    with pytest.raises(CalibrationError, match="verdict"):
        aggregate_calibration([broken], policy=POLICY, observed_at=OBSERVED)
    duplicate = [_sample(1, reviewed=False), _sample(1, reviewed=False)]
    with pytest.raises(CalibrationError, match="identity 重复"):
        aggregate_calibration(duplicate, policy=POLICY, observed_at=OBSERVED)
