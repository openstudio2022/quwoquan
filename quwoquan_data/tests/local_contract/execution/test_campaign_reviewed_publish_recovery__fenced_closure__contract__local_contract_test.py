# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""Fenced publish recovery for an already-reviewed campaign lane.

`REQ-001` binds carrier finalize to its own claim, the object-level
review/rights/provenance evidence and the publish receipt, and requires token,
generation, source or object-closure drift to fail closed; the shared canonical
publish stays single-writer behind the object transaction lock, and the final
Manifest must verify every selected object and its reference closure.
`GWT-001` adds that only the owner matching the run generation and fencing token
may finalize, that replaying the same digest is idempotent, and that a stale
claim, a foreign lane root or capsule drift are rejected.

Recovery therefore has two layers that must not be confused: a per-object
publish failure is isolated as a typed discard, while any failure touching the
shared review/rights/closure identity has to propagate instead of being demoted
to an object exclusion.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.campaign.submission import campaign_root
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.closure.publish_outcome import (
    PUBLISH_APPLY_FAILED,
    TypedPublishExclusion,
    publish_discard,
    publish_issue_code,
)
from content.execution.controller.execute import campaign_reviewed_publish_recovery
from content.execution.controller.execute.campaign_reviewed_publish_recovery import (
    recover_campaign_reviewed_publish,
)
from core.io import write_json

ROOT_ID = "20260728--travel-homepage-workload-homepage-1--china--scale-001"
ARTICLE_ID = "20260728--travel-article-workload-article-1--china--scale-001"
RECOVERY_INVALID = "DATA.CAMPAIGN.REVIEWED_PUBLISH_RECOVERY_INVALID"


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    output_root = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=output_root,
        publish_root=tmp_path / "publish",
        campaigns_root=(
            output_root / "data/local/workspace/content-campaign-submissions"
        ),
        workspaces_root=output_root / "data/local/cache/campaign-workspaces",
    )


def test_recovery_fails_closed_without_a_frozen_campaign_plan(
    tmp_path: Path,
) -> None:
    """Recovery may only run against one frozen plan, never synthesize one."""

    runtime = _runtime(tmp_path)

    with pytest.raises(ValueError) as excinfo:
        recover_campaign_reviewed_publish(
            ARTICLE_ID,
            ROOT_ID,
            runtime_paths=runtime,
        )

    assert RECOVERY_INVALID in str(excinfo.value)
    assert "frozen campaign plan" in str(excinfo.value)


def test_a_symlinked_campaign_plan_is_rejected(tmp_path: Path) -> None:
    """Frozen evidence must be one regular file so bytes stay auditable."""

    runtime = _runtime(tmp_path)
    campaign = campaign_root(ROOT_ID, root=runtime.campaigns_root)
    real_plan = tmp_path / "elsewhere" / "campaign_plan.json"
    write_json(real_plan, {"rootExecutionId": ROOT_ID})
    campaign.mkdir(parents=True, exist_ok=True)
    (campaign / "campaign_plan.json").symlink_to(real_plan)

    with pytest.raises(ValueError) as excinfo:
        recover_campaign_reviewed_publish(
            ARTICLE_ID,
            ROOT_ID,
            runtime_paths=runtime,
        )

    assert RECOVERY_INVALID in str(excinfo.value)
    assert "frozen campaign plan" in str(excinfo.value)


def test_recovery_serializes_operator_calls_per_carrier(tmp_path: Path) -> None:
    """The operator-level fence is one exclusive lock per campaign carrier."""

    runtime = _runtime(tmp_path)
    receipts = campaign_root(ROOT_ID, root=runtime.campaigns_root) / "receipts"

    with campaign_reviewed_publish_recovery._campaign_recovery_lock(
        runtime,
        ROOT_ID,
        "article",
    ):
        article_lock = receipts / ".article-reviewed-publish-recovery.lock"
        assert article_lock.is_file()

        with campaign_reviewed_publish_recovery._campaign_recovery_lock(
            runtime,
            ROOT_ID,
            "image",
        ):
            assert (receipts / ".image-reviewed-publish-recovery.lock").is_file()


def test_the_recovery_lock_lives_under_the_campaign_receipts_root(
    tmp_path: Path,
) -> None:
    """The fence belongs to the campaign, not to a lane execution root."""

    runtime = _runtime(tmp_path)

    with campaign_reviewed_publish_recovery._campaign_recovery_lock(
        runtime,
        ROOT_ID,
        "article",
    ):
        lock = (
            campaign_root(ROOT_ID, root=runtime.campaigns_root)
            / "receipts"
            / ".article-reviewed-publish-recovery.lock"
        )
        assert lock.parent.parent.name == ROOT_ID
        assert lock.parent.parent.parent == runtime.campaigns_root


@pytest.mark.parametrize(
    "message",
    [
        "predecessor review attestation is invalid",
        "review receipt/object closure drift",
        "object closure digest drift",
        "review evidence index is missing",
        "post manifest contentIdentity is absent",
        "independent review verdict is missing",
        "asset rights status is unverified",
        "publish evidence cannot be symlinked",
        "对象审核证据缺失",
        "资产授权范围不足",
        "媒体权利状态未核验",
        "引用闭包证据不完整",
    ],
)
def test_shared_review_rights_and_closure_drift_stays_a_hard_failure(
    message: str,
) -> None:
    """Shared identity drift must propagate, not become an object exclusion."""

    assert campaign_reviewed_publish_recovery._is_hard_recovery_failure(
        ValueError(message)
    ) is True


@pytest.mark.parametrize(
    "message",
    [
        "campaign fencing token is stale",
        "DATA.PUBLISH.TARGET_CONFLICT: promoted object identity drift",
        "source identity drift between plan and execution",
        "create-once receipt already exists with different bytes",
    ],
)
def test_fence_and_identity_drift_stays_a_hard_failure(message: str) -> None:
    """Token, generation and source drift are campaign-level, not per object."""

    assert campaign_reviewed_publish_recovery._is_hard_recovery_failure(
        ValueError(message)
    ) is True


def test_a_single_object_apply_failure_stays_isolated() -> None:
    """A per-object publish failure only discards that object."""

    error = RuntimeError("object apply failed for posts/article/a1")

    assert campaign_reviewed_publish_recovery._is_hard_recovery_failure(error) is False
    assert publish_issue_code(error) == PUBLISH_APPLY_FAILED


def test_a_self_typed_object_exclusion_stays_isolated() -> None:
    """A failure that names its own object-level code is not campaign-wide."""

    error = TypedPublishExclusion(
        "DATA.PUBLISH.OBJECT_CLOSURE_OVER_BUDGET",
        "object apply blocked: single-object budget exceeded",
    )

    assert campaign_reviewed_publish_recovery._is_hard_recovery_failure(error) is False
    assert publish_issue_code(error) == "DATA.PUBLISH.OBJECT_CLOSURE_OVER_BUDGET"


def test_an_isolated_discard_carries_a_non_empty_ref_and_typed_issue() -> None:
    """`REQ-001` requires every discard to carry `objectRef` and typed issues."""

    discard = publish_discard("article/攻略/都江堰/1", issue=PUBLISH_APPLY_FAILED)

    assert discard == {
        "objectRef": "article/攻略/都江堰/1",
        "issues": [PUBLISH_APPLY_FAILED],
    }


def test_a_discard_without_a_typed_issue_fails_closed() -> None:
    """A discard may not degrade into an untyped exclusion."""

    with pytest.raises(ValueError, match="requires objectRef and typed issue"):
        publish_discard("article/攻略/都江堰/1", issue="   ")


def test_a_discard_without_an_object_ref_fails_closed() -> None:
    """An anonymous discard cannot be reconciled against the closure."""

    with pytest.raises(ValueError, match="requires objectRef and typed issue"):
        publish_discard("  ", issue=PUBLISH_APPLY_FAILED)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("posts/article/攻略/都江堰/1", "article/攻略/都江堰/1"),
        ("/posts/article/攻略/都江堰/1/", "article/攻略/都江堰/1"),
        ("article/攻略/都江堰/1", "article/攻略/都江堰/1"),
        ("", ""),
        (None, ""),
    ],
)
def test_publish_refs_normalize_to_one_canonical_object_identity(
    raw: object,
    expected: str,
) -> None:
    """Replay comparison needs one canonical object ref, not two spellings."""

    assert (
        campaign_reviewed_publish_recovery._normalized_publish_ref(raw) == expected
    )


def test_publish_evidence_must_be_a_regular_file(tmp_path: Path) -> None:
    """Symlinked publish evidence would let bytes change outside the fence."""

    real = tmp_path / "real" / "publish_ref.json"
    write_json(real, {"executionId": ARTICLE_ID})
    link = tmp_path / "publish_ref.json"
    link.symlink_to(real)

    campaign_reviewed_publish_recovery._require_regular(
        real,
        label="existing publish_ref",
    )
    with pytest.raises(ValueError, match="must be one regular file"):
        campaign_reviewed_publish_recovery._require_regular(
            link,
            label="existing publish_ref",
        )


def test_absent_publish_evidence_is_reported_as_a_missing_regular_file(
    tmp_path: Path,
) -> None:
    """An absent file is a typed failure, not a silently empty outcome."""

    with pytest.raises(ValueError, match="must be one regular file"):
        campaign_reviewed_publish_recovery._require_regular(
            tmp_path / "missing.json",
            label="existing publish_ref",
        )
