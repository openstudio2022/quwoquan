# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from quwoquan_ops.ci.promotion_timing_ratchet import (
    PromotionTimingError,
    aggregate_windows,
    make_sample,
    nearest_rank_p95,
    next_budget,
    policy_digest,
    validate_policy,
    validate_sample,
    verify_monotonic,
)

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/ci/promotion_timing_ratchet.py"
POLICY_PATH = ROOT / "quwoquan_ops/policies/promotion_timing_ratchet.yaml"
POLICY = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
POLICY_DIGEST = policy_digest(POLICY)
WORKFLOW_DIGEST = "sha256:" + "2" * 64
ANCHOR = datetime(1970, 1, 1, tzinfo=timezone.utc)


def fixed_window(index: int) -> datetime:
    return ANCHOR + timedelta(days=14 * index)


def sample(
    index: int,
    ready: datetime,
    duration: int = 240,
    classification: str = "success",
    *,
    complete: bool = True,
    event_id: str | None = None,
    observation_id: str | None = None,
    run_attempt: int = 1,
    first_attempt_at: datetime | None = None,
    policy_digest_value: str = POLICY_DIGEST,
    workflow_digest: str = WORKFLOW_DIGEST,
    head_sha: str | None = None,
    repository: str = "owner/repository",
) -> dict:
    first = first_attempt_at or ready - timedelta(seconds=10)
    readback = ready + timedelta(seconds=duration) if complete else None
    observed = readback or ready + timedelta(seconds=max(duration, 1))
    return make_sample(
        observation_id=observation_id or f"delivery-{index}",
        event_id=event_id or f"event-{index}",
        repository=repository,
        workflow_run_id=str(10_000 + index),
        run_attempt=run_attempt,
        head_sha=head_sha or f"{index:040x}",
        base_sha="a" * 40,
        first_attempt_at=first.isoformat(),
        promotion_ready_at=ready.isoformat(),
        observed_at=observed.isoformat(),
        main_readback_at=readback.isoformat() if readback else None,
        classification=classification,
        evidence_complete=complete,
        policy_digest=policy_digest_value,
        workflow_digest=workflow_digest,
    )


def complete_window(window_index: int, *, duration: int = 240, offset: int = 0) -> list[dict]:
    start = fixed_window(window_index)
    return [
        sample(offset + i, start + timedelta(hours=i), duration + i)
        for i in range(30)
    ]


def test_policy_freezes_permanent_all_event_metric() -> None:
    policy = validate_policy(POLICY)
    assert policy["targetP95Seconds"] == 300
    assert policy["windowDays"] == 14
    assert policy["minimumEligibleEvents"] == 30
    assert policy["quantile"] == "nearest_rank"
    assert policy["denominator"] == "all_eligible_promotion_events"
    assert policy["attemptClock"] == "first_attempt"
    assert set(policy["classifications"]) == {
        "success", "failure", "infra", "superseded", "unclassified", "incomplete"
    }
    serialized = json.dumps(policy).lower()
    for forbidden in ("successonly", '"stage"', '"phase"', '"bypass"'):
        assert forbidden not in serialized


def test_sample_identity_fields_are_required_without_weak_defaults() -> None:
    ready = fixed_window(1000)
    with pytest.raises(TypeError, match="observation_id"):
        make_sample(
            event_id="event-1",
            repository="owner/repository",
            workflow_run_id="42",
            run_attempt=1,
            head_sha="a" * 40,
            base_sha="b" * 40,
            first_attempt_at=(ready - timedelta(seconds=10)).isoformat(),
            promotion_ready_at=ready.isoformat(),
            observed_at=(ready + timedelta(seconds=1)).isoformat(),
            main_readback_at=(ready + timedelta(seconds=1)).isoformat(),
            classification="success",
            evidence_complete=True,
            policy_digest=POLICY_DIGEST,
            workflow_digest=WORKFLOW_DIGEST,
        )
    with pytest.raises(PromotionTimingError, match="owner/name"):
        sample(1, ready, repository="")


def test_nearest_rank_and_two_consecutive_closed_windows_tighten_only_downward() -> None:
    rows = complete_window(1000, offset=0) + complete_window(1001, offset=30)
    as_of = fixed_window(1002)
    windows = aggregate_windows(rows, POLICY, as_of=as_of)
    assert [item["denominator"] for item in windows] == [30, 30]
    assert nearest_rank_p95(list(range(1, 31))) == 29
    assert next_budget(current_policy=POLICY, windows=windows) == 300


def test_all_classifications_enter_denominator_before_qualification() -> None:
    start = fixed_window(1000)
    classifications = ("success", "failure", "infra", "superseded", "unclassified", "incomplete")
    rows = []
    for index in range(30):
        classification = classifications[index % len(classifications)]
        rows.append(
            sample(
                index,
                start + timedelta(hours=index),
                classification=classification,
                complete=classification != "incomplete",
            )
        )
    window = aggregate_windows(rows, POLICY, as_of=fixed_window(1001))[0]
    assert window["denominator"] == 30
    assert window["classificationCounts"] == {name: 5 for name in classifications}
    assert sum(window["classificationCounts"].values()) == window["denominator"]
    assert window["completeSamples"] == 25
    assert window["qualified"] is False


def test_missing_window_is_materialized_and_blocks_cherry_picked_history() -> None:
    rows = complete_window(1000, offset=0) + complete_window(1002, offset=30)
    windows = aggregate_windows(rows, POLICY, as_of=fixed_window(1003))
    assert [item["windowIndex"] for item in windows] == [1000, 1001, 1002]
    assert windows[1]["denominator"] == 0
    assert windows[1]["qualified"] is False
    assert next_budget(current_policy=POLICY, windows=windows) == POLICY["enforcementBudgetSeconds"]


def test_open_window_never_qualifies() -> None:
    rows = complete_window(1000)
    window = aggregate_windows(rows, POLICY, as_of=fixed_window(1000) + timedelta(days=13))[0]
    assert window["closed"] is False
    assert window["qualified"] is False


def test_policy_epoch_cannot_mix_within_or_across_qualifying_windows() -> None:
    first = complete_window(1000, offset=0)
    second = complete_window(1001, offset=30)
    second[0] = sample(
        30,
        fixed_window(1001),
        policy_digest_value="sha256:" + "3" * 64,
    )
    windows = aggregate_windows(first + second, POLICY, as_of=fixed_window(1002))
    assert windows[1]["policyEpoch"] is None
    assert windows[1]["qualified"] is False
    assert next_budget(current_policy=POLICY, windows=windows) == POLICY["enforcementBudgetSeconds"]

    second = complete_window(1001, offset=30)
    for index, row in enumerate(second):
        second[index] = sample(
            30 + index,
            fixed_window(1001) + timedelta(hours=index),
            workflow_digest="sha256:" + "4" * 64,
        )
    windows = aggregate_windows(first + second, POLICY, as_of=fixed_window(1002))
    assert all(item["qualified"] for item in windows)
    assert next_budget(current_policy=POLICY, windows=windows) == POLICY["enforcementBudgetSeconds"]


def test_rerun_preserves_first_attempt_clock_and_first_success_readback() -> None:
    ready = fixed_window(1000)
    first = sample(
        1,
        ready,
        120,
        "failure",
        event_id="event",
        observation_id="delivery-1",
        run_attempt=1,
    )
    second = sample(
        1,
        ready,
        240,
        "success",
        event_id="event",
        observation_id="delivery-2",
        run_attempt=2,
    )
    other_rows = [
        sample(index, ready + timedelta(hours=index), observation_id=f"other-{index}") for index in range(2, 31)
    ]
    window = aggregate_windows([first, second, *other_rows], POLICY, as_of=fixed_window(1001))[0]
    assert window["denominator"] == 30
    assert window["classificationCounts"]["success"] == 30
    assert window["classificationCounts"]["failure"] == 0
    assert window["p95Seconds"] == 240

    changed_ready = dict(second)
    changed_ready["observationId"] = "delivery-3"
    changed_ready["promotionReadyAt"] = (ready + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    changed_ready["durationSeconds"] = 180
    with pytest.raises(PromotionTimingError, match="immutable first-attempt field"):
        aggregate_windows([first, changed_ready, *other_rows], POLICY, as_of=fixed_window(1001))


def test_duplicate_event_or_head_sha_makes_window_unqualified() -> None:
    ready = fixed_window(1000)
    first = sample(0, ready, observation_id="delivery-first")
    duplicate_event = sample(
        0,
        ready,
        observation_id="delivery-duplicate-event",
    )
    duplicate_sha = sample(
        29,
        ready + timedelta(hours=13),
        head_sha=first["headSha"],
    )
    other_rows = [
        sample(index, ready + timedelta(minutes=30 * index))
        for index in range(1, 29)
    ]
    window = aggregate_windows(
        [first, duplicate_event, duplicate_sha, *other_rows],
        POLICY,
        as_of=fixed_window(1001),
    )[0]
    assert window["denominator"] == POLICY["minimumEligibleEvents"]
    assert window["duplicateEvents"] >= 3
    assert window["qualified"] is False


def test_duplicate_observation_is_visible_and_conflicting_bytes_fail_closed() -> None:
    ready = fixed_window(1000)
    row = sample(1, ready)
    other_rows = [
        sample(index, ready + timedelta(hours=index), observation_id=f"other-{index}") for index in range(2, 31)
    ]
    window = aggregate_windows([row, row, *other_rows], POLICY, as_of=fixed_window(1001))[0]
    assert window["denominator"] == 30
    assert window["duplicateEvents"] == 1
    assert window["qualified"] is False

    conflicting = dict(row)
    conflicting["classification"] = "failure"
    with pytest.raises(PromotionTimingError, match="conflicting bytes"):
        aggregate_windows([row, conflicting, *other_rows], POLICY, as_of=fixed_window(1001))


def test_policy_or_workflow_epoch_drift_never_qualifies() -> None:
    rows = complete_window(1000)
    stale_policy_rows = [
        sample(
            index,
            fixed_window(1000) + timedelta(hours=index),
            policy_digest_value="sha256:" + "3" * 64,
        )
        for index in range(POLICY["minimumEligibleEvents"])
    ]
    stale = aggregate_windows(
        stale_policy_rows, POLICY, as_of=fixed_window(1001)
    )[0]
    assert stale["policyCurrent"] is False
    assert stale["qualified"] is False

    current = aggregate_windows(rows, POLICY, as_of=fixed_window(1001))[0]
    assert current["policyCurrent"] is True
    assert current["qualified"] is True


def test_missing_duration_is_null_and_never_filled_with_zero() -> None:
    row = sample(1, fixed_window(1000), classification="incomplete", complete=False)
    assert row["mainReadbackAt"] is None
    assert row["durationSeconds"] is None
    assert row["timingComplete"] is False
    assert validate_sample(row) == row


def test_monotonic_policy_blocks_widening_weakening_and_measure_drift() -> None:
    candidate = dict(POLICY)
    candidate["enforcementBudgetSeconds"] = POLICY["enforcementBudgetSeconds"] + 1
    with pytest.raises(PromotionTimingError, match="widened"):
        verify_monotonic(POLICY, candidate)

    candidate = dict(POLICY)
    candidate["consecutiveQualifiedWindows"] = POLICY["consecutiveQualifiedWindows"] - 1
    with pytest.raises(PromotionTimingError, match="weakened"):
        verify_monotonic(POLICY, candidate)

    candidate = {**POLICY, "governance": dict(POLICY["governance"])}
    candidate["governance"]["measure"] += " changed"
    with pytest.raises(PromotionTimingError, match="measure drifted"):
        verify_monotonic(POLICY, candidate)


def test_cli_sample_aggregate_recommend_and_monotonic_validation(tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.json"
    ready = fixed_window(1000)
    command = [
        sys.executable,
        str(SCRIPT),
        "sample",
        "--observation-id", "delivery-1",
        "--event-id", "event-1",
        "--repository", "owner/repository",
        "--workflow-run-id", "42",
        "--run-attempt", "1",
        "--head-sha", "a" * 40,
        "--base-sha", "b" * 40,
        "--first-attempt-at", (ready - timedelta(seconds=5)).isoformat(),
        "--promotion-ready-at", ready.isoformat(),
        "--observed-at", (ready + timedelta(seconds=240)).isoformat(),
        "--main-readback-at", (ready + timedelta(seconds=240)).isoformat(),
        "--classification", "success",
        "--evidence-complete", "true",
        "--policy-digest", POLICY_DIGEST,
        "--workflow-digest", WORKFLOW_DIGEST,
        "--write-json", str(sample_path),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([json.loads(sample_path.read_text())]), encoding="utf-8")
    aggregate_path = tmp_path / "aggregate.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "aggregate", "--policy", str(POLICY_PATH),
         "--samples", str(rows_path), "--as-of", fixed_window(1001).isoformat(),
         "--write-json", str(aggregate_path)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    recommendation_path = tmp_path / "recommendation.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "recommend", "--policy", str(POLICY_PATH),
         "--aggregate", str(aggregate_path), "--write-json", str(recommendation_path)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(recommendation_path.read_text())["action"] == "keep"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "validate-monotonic",
         "--previous-policy", str(POLICY_PATH), "--candidate-policy", str(POLICY_PATH)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
