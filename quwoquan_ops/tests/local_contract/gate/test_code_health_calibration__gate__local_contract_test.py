"""Code-health calibration remains evidence-bound and human-promoted.

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-002.t3
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from quwoquan_ops.gate.code_health_delta.calibration import aggregate_calibration
from quwoquan_ops.gate.code_health_delta.policy import load_policy

ROOT = Path(__file__).resolve().parents[4]
POLICY = load_policy(ROOT / "quwoquan_ops/policies/code_health_policy.yaml")


def _sample(number: int, *, reviewed: bool) -> dict:
    finding = {"code": "CODE_HEALTH.COMPLEXITY_ADVISORY", "path": f"quwoquan_ops/ci/{number}.py", "terminal": "PR_WARN"}
    report = {
        "schema": "quwoquan.code-health-delta.v1", "candidateSource": "commit",
        "headSha": f"{number:040x}", "terminal": "PR_WARN", "findings": [finding],
        "evidenceFingerprint": {"digest": "sha256:" + f"{number:064x}"},
    }
    reviews = [{"code": finding["code"], "path": finding["path"], "verdict": "confirmed"}] if reviewed else []
    return {"pullRequest": number, "durationSeconds": 12.0, "report": report, "findingReviews": reviews}


def test_twenty_unreviewed_prs_never_auto_promote() -> None:
    result = aggregate_calibration(
        [_sample(number, reviewed=False) for number in range(1, 21)],
        policy=POLICY,
        observed_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )
    assert result["promotion"] == {
        "sampleGate": True, "performanceGate": True, "falsePositiveGate": False,
        "eligibleForHumanPolicyRevision": False, "automaticPromotion": False,
        "recommendation": "keep-advisory",
    }
    assert result["review"]["unreviewedAdvisoryCount"] == 20


def test_reviewed_low_false_positive_fast_sample_only_recommends_human_revision() -> None:
    samples = [_sample(number, reviewed=True) for number in range(1, 21)]
    result = aggregate_calibration(samples, policy=POLICY, observed_at=datetime(2026, 9, 6, tzinfo=timezone.utc))
    assert result["promotion"]["eligibleForHumanPolicyRevision"] is True
    assert result["promotion"]["automaticPromotion"] is False
    assert result["review"]["confirmedFalsePositiveRate"] == 0.0

    slow = deepcopy(samples)
    for sample in slow[-2:]:
        sample["durationSeconds"] = 181.0
    result = aggregate_calibration(slow, policy=POLICY, observed_at=datetime(2026, 9, 6, tzinfo=timezone.utc))
    assert result["promotion"]["performanceGate"] is False
    assert result["promotion"]["eligibleForHumanPolicyRevision"] is False
