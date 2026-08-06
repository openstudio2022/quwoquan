from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from core.control_types import AgentFailureKind, AgentProvider
from core.runtime_policy import active_runtime_policy
from core.paths import DATA_RUNTIME_WORKSPACE_ROOT
from content.execution.agent.capacity_broker import (
    SemanticCapacityBroker,
    SemanticCapacityTimeout,
    SemanticProviderCircuitOpen,
    semantic_provider_capacity,
)
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.agent.agent_runner import _managed_agent_runner_for_provider


def test_semantic_capacity_is_derived_from_governed_campaign_workers() -> None:
    policy = active_runtime_policy()
    assert semantic_provider_capacity(policy) == (
        policy.campaign_lane_workers * policy.author_workers
    )


def test_semantic_capacity_runtime_state_uses_workspace_root() -> None:
    assert SemanticCapacityBroker().root == (
        DATA_RUNTIME_WORKSPACE_ROOT / "semantic-agent-capacity"
    )


def test_semantic_capacity_enforces_provider_wide_limit(tmp_path) -> None:
    broker = SemanticCapacityBroker(tmp_path)
    first = broker.acquire(
        AgentProvider.CODEX_SDK,
        lane="homepage",
        capacity=1,
        wait_timeout_seconds=1,
        lease_ttl_seconds=10,
    )
    with pytest.raises(SemanticCapacityTimeout):
        broker.acquire(
            AgentProvider.CODEX_SDK,
            lane="article",
            capacity=1,
            wait_timeout_seconds=0.02,
            lease_ttl_seconds=10,
        )
    first.release()
    with broker.acquire(
        AgentProvider.CODEX_SDK,
        lane="article",
        capacity=1,
        wait_timeout_seconds=1,
        lease_ttl_seconds=10,
    ):
        assert len(broker.snapshot(AgentProvider.CODEX_SDK)["leases"]) == 1


def test_semantic_capacity_rotates_waiting_lanes_fairly(tmp_path) -> None:
    broker = SemanticCapacityBroker(tmp_path)
    active = broker.acquire(
        AgentProvider.CODEX_SDK,
        lane="homepage",
        capacity=1,
        wait_timeout_seconds=1,
        lease_ttl_seconds=10,
    )
    order: list[str] = []

    def wait_for_lane(lane: str) -> None:
        with broker.acquire(
            AgentProvider.CODEX_SDK,
            lane=lane,
            capacity=1,
            wait_timeout_seconds=2,
            lease_ttl_seconds=10,
        ):
            order.append(lane)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(wait_for_lane, "homepage")]
        time.sleep(0.02)
        futures.append(pool.submit(wait_for_lane, "article"))
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if len(broker.snapshot(AgentProvider.CODEX_SDK)["waiters"]) == 2:
                break
            time.sleep(0.01)
        active.release()
        for future in futures:
            future.result(timeout=3)

    assert order == ["article", "homepage"]


def test_provider_rejection_opens_shared_fast_fail_circuit(tmp_path) -> None:
    clock = [100.0]
    broker = SemanticCapacityBroker(
        tmp_path,
        wall_clock=lambda: clock[0],
        pid_alive=lambda _pid: True,
    )
    broker.open_circuit(
        AgentProvider.CODEX_SDK,
        model="gpt-5.6-terra",
        failure_kind=AgentFailureKind.PROVIDER_REJECTED,
        message="usage limit reached",
        cooldown_seconds=30,
    )

    sibling = SemanticCapacityBroker(
        tmp_path,
        wall_clock=lambda: clock[0],
        pid_alive=lambda _pid: True,
    )
    with pytest.raises(SemanticProviderCircuitOpen, match="usage limit reached"):
        sibling.acquire(
            AgentProvider.CODEX_SDK,
            lane="video",
            capacity=4,
            wait_timeout_seconds=1,
            lease_ttl_seconds=10,
        )

    clock[0] = 131.0
    with sibling.acquire(
        AgentProvider.CODEX_SDK,
        lane="video",
        capacity=4,
        wait_timeout_seconds=1,
        lease_ttl_seconds=10,
    ):
        assert sibling.check_circuit(AgentProvider.CODEX_SDK) is None


def test_capacity_receipt_is_create_once_and_binds_invocation(
    tmp_path,
    monkeypatch,
) -> None:
    broker = SemanticCapacityBroker(tmp_path)
    monkeypatch.setattr(
        "content.execution.agent.capacity_broker._provider_runtime_version",
        lambda _provider: "codex-cli 1.2.3",
    )
    lease = broker.acquire(
        AgentProvider.CODEX_SDK,
        lane="article",
        capacity=4,
        wait_timeout_seconds=1,
        lease_ttl_seconds=10,
    )
    outcome = AgentRunOutcome.finished(
        provider=AgentProvider.CODEX_SDK,
        run_id="codex-run-1",
        result_text="completed",
    )
    receipt, path = broker.write_capacity_receipt(
        lease,
        execution_id="20260805--travel-article-m3--china--scale-201",
        model="gpt-5.6-terra",
        role="author",
        prompt="governed prompt",
        outcome=outcome,
        runtime_profile_id="semantic_agent_local_calibrated",
        recorded_at="2026-08-05T00:00:00Z",
    )
    repeated, repeated_path = broker.write_capacity_receipt(
        lease,
        execution_id="20260805--travel-article-m3--china--scale-201",
        model="gpt-5.6-terra",
        role="author",
        prompt="governed prompt",
        outcome=outcome,
        runtime_profile_id="semantic_agent_local_calibrated",
        recorded_at="2026-08-05T00:00:00Z",
    )
    lease.release()

    assert receipt == repeated
    assert path == repeated_path
    assert receipt["provider"] == "codex_sdk"
    assert receipt["role"] == "author"
    assert receipt["sdkVersion"] == "codex-cli 1.2.3"
    assert str(receipt["outputSchemaDigest"]).startswith("sha256:")
    assert receipt["accountScopeId"] == "default-account"
    assert receipt["hostScopeId"] == "local-host"
    assert receipt["laneCapacityLimit"] == 4
    assert receipt["runId"] == "codex-run-1"
    assert path.is_file()


def test_retry_after_circuit_preserves_retryability(tmp_path) -> None:
    broker = SemanticCapacityBroker(tmp_path, pid_alive=lambda _pid: True)
    circuit = broker.open_circuit(
        AgentProvider.CODEX_SDK,
        model="gpt-5.6-terra",
        failure_kind=AgentFailureKind.PROVIDER_REJECTED,
        message="rate limited",
        cooldown_seconds=45,
        retryable=True,
        retry_after_seconds=45,
    )

    assert circuit["retryable"] is True
    assert circuit["retryAfterSeconds"] == 45


def test_semantic_role_rejects_model_binding_drift_before_provider_launch() -> None:
    policy = active_runtime_policy()
    outcome = _managed_agent_runner_for_provider(
        SimpleNamespace(
            agent_provider=AgentProvider.CODEX_SDK,
            semantic_role="calibration",
            model_selection=policy.semantic_author.selection,
        ),
        "must not launch",
    )

    assert not outcome.succeeded
    assert outcome.error_code == "semantic_provider_role_binding_mismatch"


def test_capacity_broker_enforces_per_lane_limit_without_blocking_sibling_lane(
    tmp_path,
) -> None:
    broker = SemanticCapacityBroker(tmp_path)
    first = broker.acquire(
        AgentProvider.CODEX_SDK,
        lane="homepage",
        capacity=4,
        lane_capacity=1,
        requests_per_minute=60_000,
        burst_limit=4,
        wait_timeout_seconds=1,
        lease_ttl_seconds=10,
    )
    with pytest.raises(SemanticCapacityTimeout):
        broker.acquire(
            AgentProvider.CODEX_SDK,
            lane="homepage",
            capacity=4,
            lane_capacity=1,
            requests_per_minute=60_000,
            burst_limit=4,
            wait_timeout_seconds=0.02,
            lease_ttl_seconds=10,
        )
    with broker.acquire(
        AgentProvider.CODEX_SDK,
        lane="article",
        capacity=4,
        lane_capacity=1,
        requests_per_minute=60_000,
        burst_limit=4,
        wait_timeout_seconds=1,
        lease_ttl_seconds=10,
    ):
        assert len(broker.snapshot(AgentProvider.CODEX_SDK)["leases"]) == 2
    first.release()


def test_capacity_broker_token_bucket_refills_from_governed_rate(tmp_path) -> None:
    clock = [100.0]
    broker = SemanticCapacityBroker(tmp_path, wall_clock=lambda: clock[0])
    first = broker.acquire(
        AgentProvider.CODEX_SDK,
        lane="image",
        capacity=2,
        lane_capacity=2,
        requests_per_minute=1,
        burst_limit=1,
        wait_timeout_seconds=1,
        lease_ttl_seconds=10,
    )
    first.release()
    with pytest.raises(SemanticCapacityTimeout):
        broker.acquire(
            AgentProvider.CODEX_SDK,
            lane="video",
            capacity=2,
            lane_capacity=2,
            requests_per_minute=1,
            burst_limit=1,
            wait_timeout_seconds=0.02,
            lease_ttl_seconds=10,
        )
    clock[0] = 160.0
    with broker.acquire(
        AgentProvider.CODEX_SDK,
        lane="video",
        capacity=2,
        lane_capacity=2,
        requests_per_minute=1,
        burst_limit=1,
        wait_timeout_seconds=1,
        lease_ttl_seconds=10,
    ):
        assert broker.snapshot(AgentProvider.CODEX_SDK)["tokenBucket"]["tokens"] == 0
