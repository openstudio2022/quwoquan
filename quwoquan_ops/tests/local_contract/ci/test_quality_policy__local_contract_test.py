# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#req-001
from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quwoquan_ops.ci import validate_quality_policy as policy


def _files() -> dict[str, dict]:
    return {
        "ci_test_ownership.json": json.loads(
            (policy.ROOT / "quwoquan_ops/policies/ci_test_ownership.json").read_text()
        ),
        "flaky_test_policy.json": json.loads(
            (policy.ROOT / "quwoquan_ops/policies/flaky_test_policy.json").read_text()
        ),
        "feedback_slo_activation.json": json.loads(
            (policy.ROOT / "quwoquan_ops/environments/feedback_slo_activation.json").read_text()
        ),
    }


def _validate(files: dict[str, dict]) -> dict[str, object]:
    original = Path.read_text

    def read_text(path: Path, *args, **kwargs) -> str:
        if path.name in files:
            return json.dumps(files[path.name])
        return original(path, *args, **kwargs)

    with patch.object(Path, "read_text", read_text):
        return policy.validate(dt.datetime(2026, 9, 5, tzinfo=dt.timezone.utc))


def test_learning_policy_is_fail_closed_and_retry_is_once() -> None:
    result = _validate(_files())
    assert result["feedbackSloState"] == "learning"
    assert result["observedCleanRuns"] == 0
    assert result["quarantinedTestCount"] == 0


def test_twenty_exact_clean_runs_are_required_for_enforcement() -> None:
    files = _files()
    refs = [f"ghcr.io/example/ci-timing-summary@sha256:{index:064x}" for index in range(20)]
    files["feedback_slo_activation.json"].update(
        cleanRunEvidenceRefs=refs, observedCleanRuns=20, state="enforced"
    )
    assert _validate(files)["feedbackSloState"] == "enforced"


@pytest.mark.parametrize("mutation", [
    lambda files: files["flaky_test_policy.json"]["retry"].update(maximumFreshRetries=2),
    lambda files: files["feedback_slo_activation.json"].update(state="enforced"),
    lambda files: files["feedback_slo_activation.json"].update(observedCleanRuns=20),
])
def test_invalid_quality_controls_fail_closed(mutation) -> None:
    files = _files()
    mutation(files)
    with pytest.raises(policy.QualityPolicyError):
        _validate(files)


def test_expired_or_promotion_critical_quarantine_fails_closed() -> None:
    files = _files()
    entry = {
        "testId": "TEST-APP-LOCAL-CONTRACT", "owner": "lane/product-mainline",
        "classification": "infra", "openedAt": "2026-08-20T00:00:00Z",
        "expiresAt": "2026-08-27T00:00:00Z", "trackingIssue": "issue:1",
        "promotionCritical": True,
    }
    files["flaky_test_policy.json"]["quarantinedTests"] = [entry]
    with pytest.raises(policy.QualityPolicyError):
        _validate(files)
