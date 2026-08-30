"""GWT-008 / GWT-010：来源发现并发上限只由冻结执行策略给出。

绑定 `specs/feature-tree/discovery-content/object-homepage-coverage-scaling/`
`multi-carrier-release/spec.md` 的 `GWT-008`、`GWT-009` 与 `GWT-010`，
以及 L2 `design.md` 的 `DEC-002`、`DEC-003`。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-001.t5
from __future__ import annotations

from types import SimpleNamespace

from content.execution.agent import auto_research
from content.execution.agent.agent_checkpoint import _managed_checkpoint_job_issues
from content.execution.agent.checkpoint_prompts import _checkpoint_prompts
from content.execution.context import ExecutionContext
from content.execution.recovery import download_unresolved
from content.source.research import auto_plan_public
from core.io import write_json
from core.runtime_policy import active_runtime_policy
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def _context(execution_id: str, entity_ids: list[str]) -> ExecutionContext:
    return ExecutionContext(
        execution_id=execution_id,
        entity_ids=entity_ids,
        spec=ExecutionFixtureBuilder(
            execution_id,
            targets=tuple(
                {"name": entity_id, "entityType": "地点/景区"}
                for entity_id in entity_ids
            ),
        ).spec(),
        managed=True,
    )


def test_auto_research_concurrency_ceiling_comes_only_from_the_frozen_policy():
    execution_id = "20260724--travel-homepage-coverage--test-region-a--scale-006"
    entity_ids = [f"上限候选-{index:03d}" for index in range(8)]
    policy = _context(execution_id, entity_ids).spec.execution_policy

    assert policy.auto_research_max_concurrent_workers == 4
    assert policy.fleet_max_concurrent_workers == 2
    # 三值分离：对象下限与工作单元数都不得派生并行上限。
    assert policy.approved_quota != policy.auto_research_max_concurrent_workers
    assert policy.target_object_count != policy.auto_research_max_concurrent_workers

    # 单对象失控保护是 runtime profile 的逐对象闸门，不随批次并行上限变化。
    assert active_runtime_policy().queue_max_wall_clock_seconds == 40 * 60


def test_auto_research_dispatches_mixed_entity_types_in_one_worker_pool(monkeypatch, tmp_path):
    execution_id = "20260724--travel-homepage-coverage--test-region-a--scale-001"
    entity_ids = ["测试景区", "测试博物馆"]
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=entity_ids,
        spec=ExecutionFixtureBuilder(
            execution_id,
            targets=(
                {"name": entity_ids[0], "entityType": "地点/景区"},
                {"name": entity_ids[1], "entityType": "地点/博物馆"},
            ),
        ).spec(),
        managed=True,
    )
    worker_ceiling = ctx.spec.execution_policy.auto_research_max_concurrent_workers
    calls: list[tuple[list[str], str, int]] = []

    monkeypatch.setattr(auto_research, "_download_auto_research_lanes", lambda _ctx: {"homepage"})
    monkeypatch.setattr(download_unresolved, "_auto_research_plan_path", lambda _ctx: tmp_path / "plan.json")
    monkeypatch.setattr(auto_research, "_write_auto_research_report", lambda _ctx, report, **_kwargs: dict(report))

    def fake_write(execution_id, target_ids, *, entity_type, max_workers, **_kwargs):
        assert execution_id == ctx.execution_id
        calls.append((list(target_ids), entity_type, max_workers))
        return {"updated": [], "issues": [], "sourceUnavailable": []}

    monkeypatch.setattr(auto_plan_public, "write_auto_research_plans", fake_write)

    auto_research._run_download_auto_research(
        ctx,
        entity_ids,
        entity_type="地点/景区",
    )

    assert calls == [(entity_ids, "地点/景区", worker_ceiling)]


def test_auto_research_resume_preserves_unstarted_waves(monkeypatch, tmp_path):
    execution_id = "20260724--travel-homepage-coverage--test-region-a--scale-002"
    entity_ids = ["已完成甲", "已完成乙", "中断已完成丙", "当前未完成丁", "尚未开始戊"]
    ctx = _context(execution_id, entity_ids)
    plan_path = tmp_path / "plan.json"
    write_json(
        plan_path,
        {
            "schema": "quwoquan.content.source.auto_research_plan",
            "executionId": execution_id,
            "waveCount": 1,
            "waves": [{"scope": "primary", "entityIds": entity_ids[:2]}],
            "partialRun": True,
            # The source writer persists only the unfinished portion of the
            # interrupted wave, not the later waves that never began.
            "remainingEntityIds": [entity_ids[3]],
        },
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(auto_research, "_download_auto_research_lanes", lambda _ctx: {"homepage"})
    monkeypatch.setattr(download_unresolved, "_auto_research_plan_path", lambda _ctx: plan_path)
    monkeypatch.setattr(auto_research, "_write_auto_research_report", lambda _ctx, report, **_kwargs: dict(report))

    def fake_write(_execution_id, target_ids, **_kwargs):
        calls.append(list(target_ids))
        return {"updated": [], "issues": [], "sourceUnavailable": []}

    monkeypatch.setattr(auto_plan_public, "write_auto_research_plans", fake_write)

    auto_research._run_download_auto_research(
        ctx,
        entity_ids,
        entity_type="地点/景区",
    )

    assert calls == [[entity_ids[3], entity_ids[4]]]


def test_auto_research_report_preserves_all_lane_evidence_across_waves(
    monkeypatch,
    tmp_path,
):
    execution_id = "20260724--travel-video-coverage--test-region-a--scale-003"
    plan_path = tmp_path / "plan.json"
    ctx = SimpleNamespace(execution_id=execution_id)
    monkeypatch.setattr(
        download_unresolved,
        "_auto_research_plan_path",
        lambda _ctx: plan_path,
    )

    row_keys = (
        "updated",
        "issues",
        "candidates",
        "articleSourceDiscovery",
        "imageCollections",
        "homepageMediaCollections",
        "homepageMediaAdvisories",
        "sourceUnavailable",
        "rescueEvents",
        "videoDiscovery",
        "videoProviderFunnels",
    )

    def wave(entity_id: str) -> dict[str, object]:
        report: dict[str, object] = {
            key: [{"entityId": entity_id, "field": key}]
            for key in row_keys
        }
        report["sourceAvailability"] = {
            "readyTargets": [entity_id],
            "readyTargetCount": 1,
            "ineligibleTargets": [],
            "ineligibleTargetCount": 0,
        }
        report["throughput"] = {
            "factKind": "single_run_observation",
            "frozenMaxConcurrentWorkers": 4,
            "peakConcurrentWorkers": 3,
            "entityCount": 1,
            "elapsedSeconds": 2.0,
            "entitiesPerMinute": 30.0,
        }
        return report

    auto_research._write_auto_research_report(
        ctx,
        wave("甲"),
        scope="primary",
        entity_ids=["甲"],
    )
    aggregate = auto_research._write_auto_research_report(
        ctx,
        wave("乙"),
        scope="primary_wave_2",
        entity_ids=["乙"],
    )

    for key in row_keys:
        assert [row["entityId"] for row in aggregate[key]] == ["甲", "乙"]
    assert aggregate["sourceAvailability"]["readyTargets"] == ["甲", "乙"]
    # 冻结上限与实测峰值各自保留，聚合不得把两者压成一个 worker 数。
    assert aggregate["throughput"] == {
        "factKind": "single_run_observation",
        "frozenMaxConcurrentWorkers": 4,
        "peakConcurrentWorkers": 3,
        "entityCount": 2,
        "elapsedSeconds": 4.0,
        "entitiesPerMinute": 30.0,
        "waveCount": 2,
    }


def test_m100_auto_research_soak_is_bounded_resumable_and_create_once(
    monkeypatch,
    tmp_path,
):
    carrier_sizes = {
        "homepage": 180,
        "article": 180,
        "image": 180,
        "video": 15,
    }
    calls: dict[str, list[str]] = {carrier: [] for carrier in carrier_sizes}
    dispatch_sizes: dict[str, list[int]] = {carrier: [] for carrier in carrier_sizes}
    active_carrier = {"value": ""}
    worker_ceiling = {"value": 0}

    monkeypatch.setattr(
        auto_research,
        "_download_auto_research_lanes",
        lambda _ctx: {active_carrier["value"]},
    )
    monkeypatch.setattr(
        download_unresolved,
        "_auto_research_plan_path",
        lambda ctx: tmp_path / f"{ctx.execution_id}.json",
    )

    def fake_write(execution_id, target_ids, *, max_workers, **_kwargs):
        carrier = active_carrier["value"]
        assert f"--travel-{carrier}-" in execution_id
        assert max_workers == worker_ceiling["value"]
        dispatch_sizes[carrier].append(len(target_ids))
        calls[carrier].extend(target_ids)
        all_ids = [
            f"{carrier}-候选-{index:03d}"
            for index in range(carrier_sizes[carrier])
        ]
        ready_set = set(all_ids[:3])
        ready = [entity_id for entity_id in target_ids if entity_id in ready_set]
        unavailable = [
            {
                "entityId": entity_id,
                "issues": ["deterministic shortfall"],
                "blockers": [],
            }
            for entity_id in target_ids
            if entity_id not in ready_set
        ]
        return {
            "updated": list(target_ids),
            "issues": [],
            "candidates": [],
            "imageCollections": [],
            "homepageMediaAdvisories": [],
            "sourceUnavailable": unavailable,
            "sourceAvailability": {
                "readyTargets": ready,
                "readyTargetCount": len(ready),
                "ineligibleTargets": unavailable,
                "ineligibleTargetCount": len(unavailable),
            },
            "throughput": {
                "factKind": "single_run_observation",
                "frozenMaxConcurrentWorkers": max_workers,
                "peakConcurrentWorkers": min(max_workers, len(target_ids)),
                "entityCount": len(target_ids),
                "elapsedSeconds": float(len(target_ids)),
                "entitiesPerMinute": 60.0,
            },
        }

    monkeypatch.setattr(auto_plan_public, "write_auto_research_plans", fake_write)

    for carrier, candidate_count in carrier_sizes.items():
        active_carrier["value"] = carrier
        execution_id = (
            f"20260807--travel-{carrier}-m100-root-cause--test-region-a--scale-001"
        )
        entity_ids = [
            f"{carrier}-候选-{index:03d}" for index in range(candidate_count)
        ]
        ctx = _context(execution_id, entity_ids)
        ceiling = ctx.spec.execution_policy.auto_research_max_concurrent_workers
        worker_ceiling["value"] = ceiling
        report: dict[str, object] = {"partialRun": True}
        while report.get("partialRun"):
            report = auto_research._run_download_auto_research(
                ctx,
                entity_ids,
                entity_type="地点/景区",
            )

        # 本次待处理实体一次性交给来源发现调度器：这一层不再按上限切批，
        # 否则先完成的额度会空等本批最慢的实体。并发上限由调度器按冻结额度约束。
        assert dispatch_sizes[carrier] == [candidate_count]
        assert worker_ceiling["value"] == ceiling
        assert calls[carrier] == entity_ids
        assert len(set(calls[carrier])) == candidate_count
        assert report["sourceAvailability"]["readyTargetCount"] == 3
        assert report["sourceAvailability"]["ineligibleTargetCount"] == (
            candidate_count - 3
        )
        assert report["completedEntityCount"] == candidate_count
        assert report["remainingEntityCount"] == 0

        # A completed create-once execution is a no-op on recovery; no semantic
        # source job may be duplicated after the final checkpoint.
        call_count = len(calls[carrier])
        resumed = auto_research._run_download_auto_research(
            ctx,
            entity_ids,
            entity_type="地点/景区",
        )
        assert len(calls[carrier]) == call_count
        assert resumed["completedEntityCount"] == candidate_count


def test_auto_research_hands_back_entities_the_frozen_deadline_never_admitted(
    monkeypatch,
    tmp_path,
):
    """冻结批次截止由来源发现阶段在准入处判定，dispatch 层原样承接可续跑集合。

    截止不再由这一层按 wave 边界推断，因此未准入实体来自阶段自己的准入判定，
    dispatch 层既不重写这个集合，也不把它与已得出终态的实体混在一起。
    """
    execution_id = "20260724--travel-homepage-coverage--test-region-a--scale-007"
    entity_ids = [f"截止候选-{index:03d}" for index in range(8)]
    ctx = _context(execution_id, entity_ids)
    policy = ctx.spec.execution_policy
    deadline = policy.fleet_batch_deadline_epoch_seconds
    admitted = entity_ids[:3]
    never_admitted = entity_ids[3:]
    dispatched: list[list[str]] = []

    monkeypatch.setattr(auto_research, "_download_auto_research_lanes", lambda _ctx: {"homepage"})
    monkeypatch.setattr(download_unresolved, "_auto_research_plan_path", lambda _ctx: tmp_path / "plan.json")
    monkeypatch.setattr(auto_research, "_write_auto_research_report", lambda _ctx, report, **_kwargs: dict(report))

    def fake_write(_execution_id, target_ids, **_kwargs):
        dispatched.append(list(target_ids))
        return {
            "updated": list(admitted),
            "issues": [],
            "sourceUnavailable": [],
            "partialRun": True,
            "partialReason": "fleet_batch_deadline_exhausted",
            "fleetBatchDeadlineEpochSeconds": deadline,
            "remainingEntityIds": list(never_admitted),
            "remainingEntityCount": len(never_admitted),
        }

    monkeypatch.setattr(auto_plan_public, "write_auto_research_plans", fake_write)

    report = auto_research._run_download_auto_research(
        ctx,
        entity_ids,
        entity_type="地点/景区",
    )

    # 整个待处理集合一次交给阶段，由阶段自己在准入处停下来。
    assert dispatched == [entity_ids]
    assert report["partialRun"] is True
    assert report["partialReason"] == "fleet_batch_deadline_exhausted"
    assert report["fleetBatchDeadlineEpochSeconds"] == deadline
    assert report["remainingEntityIds"] == never_admitted
    assert report["completedEntityIds"] == admitted
    assert set(report["completedEntityIds"]).isdisjoint(report["remainingEntityIds"])


def test_download_plan_prompts_use_each_frozen_target_entity_type(
    monkeypatch,
    tmp_path,
):
    from content.execution.recovery import download_gate, stage_reset

    execution_id = "20260724--travel-image-coverage--test-region-a--scale-004"
    targets = (
        {"name": "异构景区甲", "entityType": "地点/景区"},
        {"name": "异构打卡地乙", "entityType": "地点/打卡地"},
    )
    builder = ExecutionFixtureBuilder(execution_id, targets=targets)
    builder.build()
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=tuple(str(target["name"]) for target in targets),
        spec=builder.spec(),
        managed=True,
    )
    monkeypatch.setattr(stage_reset, "_source_plan_filled", lambda _ctx: (False, ["missing"]))
    monkeypatch.setattr(
        download_gate,
        "_download_research_lane_issues",
        lambda _ctx, _entity, _etype, lane: ["missing"] if lane == "image" else [],
    )
    monkeypatch.setattr(
        download_gate,
        "_download_repair_path",
        lambda _ctx: tmp_path / "missing-download-repair.json",
    )
    monkeypatch.setattr(
        "content.execution.agent.checkpoint_prompts.issue_messages",
        lambda values: [str(value) for value in values],
    )

    prompts = _checkpoint_prompts(ctx, "download_plan")

    prompt_by_entity = {
        next(
            line.removeprefix("对象: ")
            for line in prompt.splitlines()
            if line.startswith("对象: ")
        ): prompt
        for prompt in prompts
    }
    assert "/entities/地点/景区/异构景区甲/1.download/image_source_plan.json" in (
        prompt_by_entity["异构景区甲"]
    )
    assert "/entities/地点/打卡地/异构打卡地乙/1.download/image_source_plan.json" in (
        prompt_by_entity["异构打卡地乙"]
    )


def test_download_plan_job_gate_reads_the_prompt_entity_from_its_frozen_type(
    monkeypatch,
):
    execution_id = "20260724--travel-image-coverage--test-region-a--scale-005"
    target = {"name": "冻结景区甲", "entityType": "地点/景区"}
    builder = ExecutionFixtureBuilder(execution_id, targets=(target,))
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=(str(target["name"]),),
        spec=builder.spec(),
        managed=True,
    )
    observed_types: list[str] = []

    def record_type(_ctx, _entity, entity_type, _lane):
        observed_types.append(entity_type)
        return []

    monkeypatch.setattr(download_unresolved, "_pending_download_repair_unresolved", lambda _ctx: {})
    monkeypatch.setattr(
        "content.execution.recovery.download_gate._download_research_lane_issues",
        record_type,
    )

    issues = _managed_checkpoint_job_issues(
        ctx,
        stage="download_plan",
        prompt="[AGENT_LANE:image]\n对象: 冻结景区甲\n",
    )

    assert issues == []
    assert observed_types == ["地点/景区"]
