"""Pool delivery preserves reviewed truth across transport outages.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.closure.pool_delivery import (
    validate_pool_delivery_intent_for_job,
)
from content.execution.controller.execute import drain_pool_delivery as delivery_drain
from content.execution.queue.reliabletask import fleet as reliabletask_fleet
from content.execution.queue.reliabletask import publish_reconciliation
from core.control_types import (
    ExecutionStage,
    ExecutionStateStatus,
    QueueJobStage,
    ReliableTaskDispatchStatus,
)
from core.data_issue import (
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from support.pool_delivery_fixture import DATA_ROOT, EXECUTION_ID, _DIGEST


def test_publish_fleet_delivers_partial_reviewed_closure_below_semantic_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "content.execution.store.load_spec",
        lambda _execution_id: {"executionPolicy": {"approvedQuota": 12}},
    )
    monkeypatch.setattr(reliabletask_fleet, "_load_jobs", lambda _execution_id: [])

    assert (
        reliabletask_fleet._remaining_quota(
            EXECUTION_ID,
            QueueJobStage.PUBLISH,
            active_job_count=5,
        )
        == 5
    )
    with pytest.raises(ValueError, match="候选池耗尽"):
        reliabletask_fleet._remaining_quota(
            EXECUTION_ID,
            QueueJobStage.AUTHOR,
            active_job_count=5,
        )



def test_pool_delivery_drain__down_then_ready_consumes_same_intent_without_semantic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(stage=QueueJobStage.PUBLISH, job_id="publish-001")
    intent_id = "sha256:" + "7" * 64
    dispatch_calls: list[tuple[str, ExecutionStage]] = []
    semantic_calls: list[str] = []
    outcomes = iter(
        (
            SimpleNamespace(
                status=ReliableTaskDispatchStatus.WAITING,
                attempted_count=0,
                completed_count=0,
                issues=(
                    data_issue(
                        DataIssueCode.POOL_DELIVERY_UNAVAILABLE,
                        stage=DataIssueStage.PUBLISH,
                        recovery=DataRecoveryAction.RETRY_DELIVERY,
                        message="data-local transport unavailable",
                    ),
                ),
            ),
            SimpleNamespace(
                status=ReliableTaskDispatchStatus.COMPLETED,
                attempted_count=1,
                completed_count=1,
                issues=(),
            ),
        )
    )
    frozen_spec = SimpleNamespace(
        execution_policy=SimpleNamespace(fleet_max_concurrent_workers=1)
    )

    monkeypatch.setattr(
        delivery_drain, "load_frozen_execution_manifest", lambda _execution_id: {}
    )
    monkeypatch.setattr(delivery_drain.store, "load_spec", lambda _execution_id: {})
    monkeypatch.setattr(
        delivery_drain.ExecutionSpec,
        "from_mapping",
        lambda _payload: frozen_spec,
    )
    monkeypatch.setattr(
        delivery_drain,
        "ExecutionContext",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        delivery_drain, "coverage_entity_ids", lambda _payload: ("chengdu",)
    )
    monkeypatch.setattr(delivery_drain, "_load_jobs", lambda _execution_id: (job,))
    monkeypatch.setattr(
        delivery_drain,
        "validate_pool_delivery_intent_for_job",
        lambda candidate: {"intentId": intent_id} if candidate is job else {},
    )

    def dispatch(ctx, stage):
        dispatch_calls.append((ctx.execution_id, stage))
        return next(outcomes)

    monkeypatch.setattr(
        delivery_drain, "dispatch_reliabletask_checkpoint", dispatch
    )
    monkeypatch.setattr(
        "content.execution.agent.agent_runner._managed_agent_runner_for_provider",
        lambda *_args, **_kwargs: semantic_calls.append("called"),
    )

    pending = delivery_drain.drain_pool_delivery(EXECUTION_ID)
    recovered = delivery_drain.drain_pool_delivery(EXECUTION_ID)

    assert pending["status"] == "waiting"
    assert pending["issueCodes"] == ["DATA.POOL.DELIVERY_UNAVAILABLE"]
    assert recovered["status"] == "completed"
    assert pending["intentIds"] == recovered["intentIds"] == [intent_id]
    assert dispatch_calls == [
        (EXECUTION_ID, ExecutionStage.PUBLISH),
        (EXECUTION_ID, ExecutionStage.PUBLISH),
    ]
    assert semantic_calls == []


def test_pool_delivery_drain__reconciles_remote_dead_receipt_after_local_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = SimpleNamespace(stage=QueueJobStage.PUBLISH, job_id="publish-001")
    intent_id = "sha256:" + "7" * 64
    frozen_spec = SimpleNamespace(
        execution_policy=SimpleNamespace(fleet_max_concurrent_workers=1)
    )
    report = SimpleNamespace(
        passed=True,
        succeeded=1,
        outcomes=(SimpleNamespace(attempts=3),),
    )
    monkeypatch.setattr(
        delivery_drain, "load_frozen_execution_manifest", lambda _execution_id: {}
    )
    monkeypatch.setattr(delivery_drain.store, "load_spec", lambda _execution_id: {})
    monkeypatch.setattr(
        delivery_drain.ExecutionSpec,
        "from_mapping",
        lambda _payload: frozen_spec,
    )
    monkeypatch.setattr(
        delivery_drain,
        "ExecutionContext",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        delivery_drain, "coverage_entity_ids", lambda _payload: ("chengdu",)
    )
    monkeypatch.setattr(delivery_drain, "_load_jobs", lambda _execution_id: (job,))
    monkeypatch.setattr(
        delivery_drain,
        "validate_pool_delivery_intent_for_job",
        lambda candidate: {"intentId": intent_id} if candidate is job else {},
    )
    monkeypatch.setattr(
        delivery_drain, "dispatch_reliabletask_checkpoint", lambda *_args: None
    )
    reconcile_calls: list[str] = []

    def reconcile(execution_id: str):
        reconcile_calls.append(execution_id)
        return report

    monkeypatch.setattr(
        publish_reconciliation,
        "reconcile_frozen_publish_recovery",
        reconcile,
    )

    result = delivery_drain.drain_pool_delivery(EXECUTION_ID)

    assert result["status"] == "completed"
    assert result["executionStatePreserved"] is True
    assert result["qualifiedCount"] == result["completedCount"] == 1
    assert result["attemptedCount"] == 3
    assert result["intentIds"] == [intent_id]
    assert reconcile_calls == [EXECUTION_ID]


def test_pool_delivery_drain__pre_capsule_promotes_only_qualified_reviewed_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qualified = SimpleNamespace(
        object_ref="qualified-object",
        publish_ref="posts/article/china/travel/qualified-post",
    )
    discarded = SimpleNamespace(
        object_ref="discarded-object",
        publish_ref="posts/article/china/travel/discarded-post",
    )
    closure = SimpleNamespace(
        carrier="article",
        qualified=(qualified,),
        discarded=(discarded,),
    )
    state = SimpleNamespace(
        status=ExecutionStateStatus.MANUAL_REQUIRED,
        last_failed_stage="publish",
    )
    intent = {"intentId": "sha256:" + "8" * 64}
    writes: list[tuple[str, str]] = []
    promotions: list[str] = []
    canonical = {
        "transactionId": "transaction-qualified",
        "applyReportRef": "data/local/qualified/apply_report.json",
        "canonicalObjectRef": "posts/article/china/travel/qualified-post",
        "canonicalObjectSha256": "sha256:" + "9" * 64,
        "objectClosureDigest": "sha256:" + "a" * 64,
    }

    monkeypatch.setattr(
        delivery_drain,
        "load_frozen_execution_manifest",
        lambda _execution_id: {
            "sourceDigest": {"digest": _DIGEST},
            "executionBundle": {"digest": _DIGEST},
        },
    )
    monkeypatch.setattr(delivery_drain, "_load_jobs", lambda _execution_id: ())
    monkeypatch.setattr(delivery_drain, "load_execution_state", lambda _id: state)
    monkeypatch.setattr(
        "content.execution.closure.post_review.indexed_post_targets",
        lambda _id: {
            qualified.object_ref: qualified.publish_ref,
            discarded.object_ref: discarded.publish_ref,
        },
    )
    monkeypatch.setattr(
        "content.execution.closure.post_review.load_post_review_closure",
        lambda *_args, **_kwargs: closure,
    )

    def write_intent(_execution_id, *, object_ref, content_object_dir, **_kwargs):
        writes.append((object_ref, content_object_dir))
        return intent, Path("intent.json")

    def promote(_execution_id, post_ref, *, pool_delivery_intent):
        assert pool_delivery_intent is intent
        promotions.append(post_ref)
        return canonical

    monkeypatch.setattr(
        "content.execution.closure.pool_delivery.write_pool_delivery_intent",
        write_intent,
    )
    monkeypatch.setattr(
        "content.release.canonical.post_promotion.promote_post_object",
        promote,
    )

    result = delivery_drain.drain_pool_delivery(EXECUTION_ID)

    assert result["status"] == "completed"
    assert result["recoveryMode"] == "reviewed_delivery_only"
    assert result["executionStatePreserved"] is True
    assert result["qualifiedCount"] == result["attemptedCount"] == 1
    assert result["discardedCount"] == 1
    assert result["completedCount"] == 1
    assert writes == [(qualified.object_ref, qualified.publish_ref)]
    assert promotions == [qualified.publish_ref]
    assert result["canonicalObjects"] == [canonical]


@pytest.mark.parametrize(
    ("manifest", "status", "last_failed_stage"),
    (
        ({"sourceDigest": {"digest": _DIGEST}}, ExecutionStateStatus.MANUAL_REQUIRED, "publish"),
        (
            {"sourceDigest": {"digest": _DIGEST}, "executionBundle": {"digest": _DIGEST}},
            ExecutionStateStatus.RUNNING,
            "publish",
        ),
        (
            {"sourceDigest": {"digest": _DIGEST}, "executionBundle": {"digest": _DIGEST}},
            ExecutionStateStatus.MANUAL_REQUIRED,
            "post_review",
        ),
    ),
)
def test_pool_delivery_drain__pre_capsule_admission_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    manifest: dict[str, object],
    status: ExecutionStateStatus,
    last_failed_stage: str,
) -> None:
    monkeypatch.setattr(
        delivery_drain,
        "load_frozen_execution_manifest",
        lambda _execution_id: manifest,
    )
    monkeypatch.setattr(delivery_drain, "_load_jobs", lambda _execution_id: ())
    monkeypatch.setattr(
        delivery_drain,
        "load_execution_state",
        lambda _id: SimpleNamespace(
            status=status,
            last_failed_stage=last_failed_stage,
        ),
    )

    with pytest.raises(ValueError, match="DATA.POOL.DELIVERY_ONLY_INVALID"):
        delivery_drain.drain_pool_delivery(EXECUTION_ID)


def test_pool_delivery_drain_is_exposed_only_through_canonical_data_cli() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(DATA_ROOT / "scripts/cli.py"),
            "task",
            "drain-pool-delivery",
            "--help",
        ],
        cwd=DATA_ROOT.parent,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--execution-id" in completed.stdout
