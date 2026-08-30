"""来源发现有界并发调度器的 deterministic 调度语义。

冻结场景是 8 worker × 180 entity：并发上限、逐实体终态、失败与超时后的额度接管、
以及阶段报告如实记录的运行事实，全部由注入的可控 runtime（虚拟时钟 + 可控 future）
断言，不依赖真实 sleep、真实线程调度或真实网络。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t5
from __future__ import annotations

from typing import Any, Callable, Mapping

import pytest

from content.source.research.source_discovery_scheduler import (
    SINGLE_RUN_OBSERVATION,
    SourceDiscoveryOutcome,
    SourceDiscoveryStopReason,
    StageProgressSnapshot,
    run_bounded_source_discovery,
)
from support.source_discovery_scheduler_runtime import (
    ControlledRuntime,
    WorkerScript,
    completes,
    fails,
    hangs,
)

FROZEN_CEILING = 8
FROZEN_ENTITY_COUNT = 180
FROZEN_ENTITY_TIMEOUT_SECONDS = 60.0
FROZEN_HEARTBEAT_INTERVAL_SECONDS = 30.0


def _run(
    scripts: Mapping[str, WorkerScript],
    *,
    entity_ids: list[str],
    ceiling: int = FROZEN_CEILING,
    on_terminal: Callable[[Any, StageProgressSnapshot], None] | None = None,
    on_heartbeat: Callable[[StageProgressSnapshot], None] | None = None,
) -> tuple[Any, ControlledRuntime]:
    runtime = ControlledRuntime(scripts)
    heartbeats: list[StageProgressSnapshot] = []

    def _terminal(outcome: Any, progress: StageProgressSnapshot) -> None:
        # 超时终结的实体在生产 runtime 上不可抢占，可控 runtime 用显式释放表达
        # 「调度器账上的额度已经还回来了」。
        runtime.release_slot_on_timeout(outcome.entity_id)
        if on_terminal is not None:
            on_terminal(outcome, progress)

    run = run_bounded_source_discovery(
        entity_ids,
        frozen_max_concurrent_workers=ceiling,
        entity_timeout_seconds=FROZEN_ENTITY_TIMEOUT_SECONDS,
        heartbeat_interval_seconds=FROZEN_HEARTBEAT_INTERVAL_SECONDS,
        runtime=runtime,
        on_heartbeat=on_heartbeat or heartbeats.append,
        on_terminal=_terminal,
    )
    return run, runtime


def _frozen_scale_entity_ids() -> list[str]:
    return [f"来源发现候选-{index:03d}" for index in range(FROZEN_ENTITY_COUNT)]


def test_running_worker_count_never_exceeds_the_frozen_ceiling_at_any_scale():
    """GWT-001.t1：峰值只由冻结上限决定，不随实体数增长。"""
    entity_ids = _frozen_scale_entity_ids()
    scripts = {
        entity_id: completes(1.0 + index % 5)
        for index, entity_id in enumerate(entity_ids)
    }

    run, runtime = _run(scripts, entity_ids=entity_ids)

    assert max(runtime.observed_live_counts) == FROZEN_CEILING
    assert run.measured_peak_concurrent_workers == FROZEN_CEILING
    assert run.frozen_max_concurrent_workers == FROZEN_CEILING

    # 同一冻结上限下把实体数减到 1/4，峰值不跟着实体数走。
    quarter = entity_ids[: FROZEN_ENTITY_COUNT // 4]
    smaller_run, smaller_runtime = _run(
        {entity_id: scripts[entity_id] for entity_id in quarter},
        entity_ids=quarter,
    )
    assert max(smaller_runtime.observed_live_counts) == FROZEN_CEILING
    assert smaller_run.measured_peak_concurrent_workers == FROZEN_CEILING


def test_every_entity_reaches_exactly_one_terminal_outcome():
    """GWT-001.t2：180 个实体各自一个终态，没有丢弃、跳过或合并。"""
    entity_ids = _frozen_scale_entity_ids()
    scripts: dict[str, WorkerScript] = {}
    for index, entity_id in enumerate(entity_ids):
        if index % 12 == 5:
            scripts[entity_id] = fails(2.0, "source discovery worker exploded")
        elif index % 30 == 7:
            scripts[entity_id] = hangs()
        else:
            scripts[entity_id] = completes(1.0 + index % 4)

    run, _runtime = _run(scripts, entity_ids=entity_ids)

    assert run.stop_reason is SourceDiscoveryStopReason.ALL_ENTITIES_TERMINAL
    assert run.abandoned_entity_ids == ()
    assert len(run.outcomes) == FROZEN_ENTITY_COUNT
    assert [row.entity_id for row in run.outcomes] != []
    assert sorted(row.entity_id for row in run.outcomes) == sorted(entity_ids)
    assert len({row.entity_id for row in run.outcomes}) == FROZEN_ENTITY_COUNT

    counts = {outcome: 0 for outcome in SourceDiscoveryOutcome}
    for row in run.outcomes:
        counts[row.outcome] += 1
    expected_failed = sum(1 for index in range(FROZEN_ENTITY_COUNT) if index % 12 == 5)
    expected_timed_out = sum(
        1
        for index in range(FROZEN_ENTITY_COUNT)
        if index % 12 != 5 and index % 30 == 7
    )
    assert counts[SourceDiscoveryOutcome.FAILED] == expected_failed
    assert counts[SourceDiscoveryOutcome.TIMED_OUT] == expected_timed_out
    assert counts[SourceDiscoveryOutcome.SUCCEEDED] == (
        FROZEN_ENTITY_COUNT - expected_failed - expected_timed_out
    )
    assert sum(counts.values()) == FROZEN_ENTITY_COUNT

    # 失败与超时终态不携带实体报告，成功终态必须携带；两者不互相冒充。
    for row in run.outcomes:
        if row.outcome is SourceDiscoveryOutcome.SUCCEEDED:
            assert row.report is not None
            assert row.failure_text == ""
        else:
            assert row.report is None
            assert row.failure_text


def test_a_failed_entity_releases_its_slot_to_the_next_pending_entity():
    """GWT-001.t3：单实体失败只终结该实体，额度被下一个待处理实体接管。"""
    entity_ids = _frozen_scale_entity_ids()
    victim = entity_ids[2]
    scripts = {
        entity_id: completes(50.0) for entity_id in entity_ids
    }
    # 首批 8 个里只有一个立刻失败，其余在同一批里继续跑。
    scripts[victim] = fails(1.0, "deterministic source discovery failure")

    takeover: list[str] = []

    def _terminal(outcome: Any, _progress: StageProgressSnapshot) -> None:
        takeover.append(outcome.entity_id)

    run, runtime = _run(scripts, entity_ids=entity_ids, on_terminal=_terminal)

    first_batch = entity_ids[:FROZEN_CEILING]
    assert runtime.submission_order[:FROZEN_CEILING] == first_batch
    # 第一个终态就是那个失败实体，接管它额度的正是冻结顺序里的下一个待处理实体。
    assert takeover[0] == victim
    assert runtime.submission_order[FROZEN_CEILING] == entity_ids[FROZEN_CEILING]
    assert runtime.submission_instants[entity_ids[FROZEN_CEILING]] == (
        runtime.submission_instants[victim] + 1.0
    )
    # 其余同批实体没有被这次失败牵连，各自跑到自己的终态。
    assert run.outcome_of(victim) is SourceDiscoveryOutcome.FAILED
    for entity_id in first_batch:
        if entity_id == victim:
            continue
        assert run.outcome_of(entity_id) is SourceDiscoveryOutcome.SUCCEEDED
    assert len(run.outcomes) == FROZEN_ENTITY_COUNT


def test_a_timed_out_entity_releases_its_slot_to_the_next_pending_entity():
    """GWT-001.t3：单实体超时只终结该实体，其余实体继续跑到各自终态。"""
    entity_ids = _frozen_scale_entity_ids()
    hung = entity_ids[0]
    scripts = {entity_id: completes(5.0) for entity_id in entity_ids}
    scripts[hung] = hangs()

    run, runtime = _run(scripts, entity_ids=entity_ids)

    assert run.outcome_of(hung) is SourceDiscoveryOutcome.TIMED_OUT
    timed_out_at = runtime.submission_instants[hung] + FROZEN_ENTITY_TIMEOUT_SECONDS
    # 挂起实体占住的额度在超时那一刻被拿回：此后仍有实体被提交，队列没有停下来。
    submitted_after_timeout = [
        entity_id
        for entity_id, instant in runtime.submission_instants.items()
        if instant >= timed_out_at
    ]
    assert submitted_after_timeout
    assert len(run.outcomes) == FROZEN_ENTITY_COUNT
    assert (
        sum(
            1
            for row in run.outcomes
            if row.outcome is SourceDiscoveryOutcome.TIMED_OUT
        )
        == 1
    )
    assert max(runtime.observed_live_counts) == FROZEN_CEILING


def test_stage_report_states_the_frozen_ceiling_and_the_measured_peak_separately():
    """GWT-001.t4：报告如实记录实测峰值与冻结上限，两者是两个词元。"""
    # 实体数少于冻结上限时，实测峰值就是实体数，不会被冻结上限顶替。
    entity_ids = [f"来源发现候选-{index:03d}" for index in range(3)]
    scripts = {entity_id: completes(2.0) for entity_id in entity_ids}

    run, runtime = _run(scripts, entity_ids=entity_ids)

    assert max(runtime.observed_live_counts) == 3
    facts = run.throughput_facts(scope_entity_count=len(entity_ids), elapsed_seconds=6.0)
    assert facts["frozenMaxConcurrentWorkers"] == FROZEN_CEILING
    assert facts["peakConcurrentWorkers"] == 3
    assert facts["frozenMaxConcurrentWorkers"] != facts["peakConcurrentWorkers"]
    assert facts["entityCount"] == 3


def test_elapsed_and_rate_are_declared_as_single_run_observations():
    """GWT-001.t5：耗时与每分钟实体数自带「本次运行事实」声明位。"""
    entity_ids = _frozen_scale_entity_ids()
    scripts = {entity_id: completes(4.0) for entity_id in entity_ids}

    run, _runtime = _run(scripts, entity_ids=entity_ids)

    facts = run.throughput_facts(
        scope_entity_count=FROZEN_ENTITY_COUNT,
        elapsed_seconds=90.0,
    )
    assert facts["factKind"] == SINGLE_RUN_OBSERVATION
    assert facts["elapsedSeconds"] == 90.0
    assert facts["entitiesPerMinute"] == 120.0
    # 事实字典里没有任何稳态吞吐或容量结论词元。
    assert set(facts) == {
        "factKind",
        "frozenMaxConcurrentWorkers",
        "peakConcurrentWorkers",
        "entityCount",
        "elapsedSeconds",
        "entitiesPerMinute",
    }


def test_the_frozen_batch_deadline_stops_admission_without_losing_entities():
    """冻结批次截止到点后不再准入，已在跑的实体跑完，未准入的原样交回续跑。"""
    entity_ids = _frozen_scale_entity_ids()
    scripts = {entity_id: completes(10.0) for entity_id in entity_ids}
    runtime = ControlledRuntime(scripts)
    # 第一批 8 个各跑 10s；截止设在 25s 处，因此第三批之后不再准入。
    admission_deadline = runtime.started_at + 25.0

    run = run_bounded_source_discovery(
        entity_ids,
        frozen_max_concurrent_workers=FROZEN_CEILING,
        entity_timeout_seconds=FROZEN_ENTITY_TIMEOUT_SECONDS,
        heartbeat_interval_seconds=FROZEN_HEARTBEAT_INTERVAL_SECONDS,
        runtime=runtime,
        on_heartbeat=lambda _progress: None,
        admission_deadline_seconds=admission_deadline,
    )

    assert run.stop_reason is SourceDiscoveryStopReason.ADMISSION_DEADLINE_REACHED
    admitted = set(runtime.submission_order)
    assert all(
        instant < admission_deadline
        for instant in runtime.submission_instants.values()
    )
    # 每个实体要么得出终态，要么原样交回，两个集合不重叠也不丢人。
    terminal = {row.entity_id for row in run.outcomes}
    handed_back = set(run.abandoned_entity_ids)
    assert terminal == admitted
    assert terminal.isdisjoint(handed_back)
    assert terminal | handed_back == set(entity_ids)
    assert list(run.abandoned_entity_ids) == [
        entity_id for entity_id in entity_ids if entity_id not in admitted
    ]
    assert max(runtime.observed_live_counts) == FROZEN_CEILING


def test_the_concurrency_ceiling_must_be_a_positive_frozen_integer():
    """冻结上限缺失或非法时装配期判否，不静默退化为某个默认并发数。"""
    with pytest.raises(ValueError, match="frozen"):
        run_bounded_source_discovery(
            ["来源发现候选-000"],
            frozen_max_concurrent_workers=0,
            entity_timeout_seconds=FROZEN_ENTITY_TIMEOUT_SECONDS,
            heartbeat_interval_seconds=FROZEN_HEARTBEAT_INTERVAL_SECONDS,
            runtime=ControlledRuntime({}),
            on_heartbeat=lambda _progress: None,
        )
