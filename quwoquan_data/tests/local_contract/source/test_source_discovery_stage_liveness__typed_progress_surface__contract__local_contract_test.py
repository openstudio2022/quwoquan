"""来源发现阶段存活与进度的 typed 判定。

心跳按冻结间隔独立于任何单个实体的终态推进；存活读取只凭统一进度面返回 typed 结果，
不读取连接数、CPU 占用、进程表或文件 mtime 猜测。时钟整体注入，断言不依赖真实等待。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t7
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t8
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t9
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/source-discovery-scale-reliability/spec.md#gwt-002.t10
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from content.source.research.stage_liveness import (
    SINGLE_RUN_OBSERVATION,
    StageLivenessKind,
    StageStatus,
    read_stage_liveness,
    write_source_discovery_progress,
)

EXECUTION_ID = "20260807--travel-homepage-m100-root-cause--test-region-a--scale-001"
FROZEN_HEARTBEAT_INTERVAL_SECONDS = 30
FROZEN_HEARTBEAT_STALE_AFTER_SECONDS = 90
FROZEN_CEILING = 8
CANDIDATE_ENTITY_COUNT = 180
START_EPOCH_SECONDS = 1_800_000_000


def _write(
    path: Path,
    *,
    status: StageStatus,
    now_epoch_seconds: int,
    terminal_entity_count: int = 0,
    running_entity_ids: tuple[str, ...] = ("来源发现候选-000",),
    last_heartbeat_epoch_seconds: int | None = None,
    last_terminal_entity_id: str = "",
) -> dict:
    return write_source_discovery_progress(
        EXECUTION_ID,
        status=status,
        candidate_entity_count=CANDIDATE_ENTITY_COUNT,
        terminal_entity_count=terminal_entity_count,
        running_entity_ids=running_entity_ids,
        frozen_max_concurrent_workers=FROZEN_CEILING,
        heartbeat_interval_seconds=FROZEN_HEARTBEAT_INTERVAL_SECONDS,
        heartbeat_stale_after_seconds=FROZEN_HEARTBEAT_STALE_AFTER_SECONDS,
        elapsed_seconds=float(now_epoch_seconds - START_EPOCH_SECONDS),
        now_epoch_seconds=now_epoch_seconds,
        last_heartbeat_epoch_seconds=last_heartbeat_epoch_seconds,
        last_terminal_entity_id=last_terminal_entity_id,
        path=path,
    )


def test_heartbeat_advances_before_any_entity_reaches_a_terminal_outcome(tmp_path):
    """GWT-002.t1：首个实体终态之前，进度面仍按冻结间隔推进，最近心跳时刻前移。"""
    path = tmp_path / "auto_research_progress.json"
    readings = []
    for beat_index in range(1, 4):
        instant = START_EPOCH_SECONDS + beat_index * FROZEN_HEARTBEAT_INTERVAL_SECONDS
        _write(path, status=StageStatus.RUNNING, now_epoch_seconds=instant)
        readings.append(read_stage_liveness(path, now_epoch_seconds=instant))

    assert [reading.kind for reading in readings] == [
        StageLivenessKind.PROGRESSING
    ] * 3
    heartbeats = [reading.last_heartbeat_epoch_seconds for reading in readings]
    assert heartbeats == sorted(heartbeats)
    assert len(set(heartbeats)) == 3
    # 心跳前移与「有没有实体得出终态」无关：三次心跳期间终态数一直是 0。
    assert {reading.terminal_entity_count for reading in readings} == {0}
    assert heartbeats[-1] - heartbeats[0] == 2 * FROZEN_HEARTBEAT_INTERVAL_SECONDS


def test_liveness_reads_only_the_progress_surface(tmp_path):
    """GWT-002.t2：判定只凭进度面内容与当前时刻，不读文件 mtime 或进程旁证。"""
    path = tmp_path / "auto_research_progress.json"
    _write(path, status=StageStatus.RUNNING, now_epoch_seconds=START_EPOCH_SECONDS)
    silent_now = (
        START_EPOCH_SECONDS + FROZEN_HEARTBEAT_STALE_AFTER_SECONDS + 1
    )

    stale = read_stage_liveness(path, now_epoch_seconds=silent_now)
    assert stale.kind is StageLivenessKind.STALE_WHILE_RUNNING

    # 把 mtime 推到「现在」：如果判定偷看了文件时间，这里会翻回存活。
    os.utime(path, (silent_now, silent_now))
    assert (
        read_stage_liveness(path, now_epoch_seconds=silent_now).kind
        is StageLivenessKind.STALE_WHILE_RUNNING
    )
    # 反过来，把 mtime 推到很久以前也不会让仍在心跳的阶段被判为过期。
    os.utime(path, (START_EPOCH_SECONDS - 10_000, START_EPOCH_SECONDS - 10_000))
    fresh_now = START_EPOCH_SECONDS + FROZEN_HEARTBEAT_INTERVAL_SECONDS
    assert (
        read_stage_liveness(path, now_epoch_seconds=fresh_now).kind
        is StageLivenessKind.PROGRESSING
    )


def test_zero_terminal_entities_is_present_and_empty_not_absent(tmp_path):
    """GWT-002.t3/t4/t5：候选总数已知、终态数为 0、状态运行中，且可读出在跑实体。"""
    path = tmp_path / "auto_research_progress.json"
    running = ("来源发现候选-000", "来源发现候选-001", "来源发现候选-002")
    _write(
        path,
        status=StageStatus.RUNNING,
        now_epoch_seconds=START_EPOCH_SECONDS,
        terminal_entity_count=0,
        running_entity_ids=running,
    )

    reading = read_stage_liveness(path, now_epoch_seconds=START_EPOCH_SECONDS)

    assert reading.kind is StageLivenessKind.PROGRESSING
    assert reading.candidate_entity_count == CANDIDATE_ENTITY_COUNT
    assert reading.terminal_entity_count == 0
    assert reading.status is StageStatus.RUNNING
    assert reading.running_entity_ids == running
    # 在场为空不是缺席、不是已终止、也不是零计数失败。
    assert reading.kind is not StageLivenessKind.PROGRESS_ABSENT
    assert reading.kind is not StageLivenessKind.TERMINATED_NO_FURTHER_HEARTBEAT
    assert not reading.is_failure
    # 尚未有实体得出终态时不写空字符串的最近终态实体键。
    document = json.loads(path.read_text(encoding="utf-8"))
    assert "lastTerminalEntityId" not in document


def test_stale_while_running_and_terminated_are_distinct_readings(tmp_path):
    """GWT-002.t7：运行中未按间隔心跳与已终止不会再心跳是两个结果，不合并。"""
    running_path = tmp_path / "running_progress.json"
    _write(
        running_path,
        status=StageStatus.RUNNING,
        now_epoch_seconds=START_EPOCH_SECONDS,
    )
    silent_now = START_EPOCH_SECONDS + FROZEN_HEARTBEAT_STALE_AFTER_SECONDS + 1
    stale = read_stage_liveness(running_path, now_epoch_seconds=silent_now)

    terminated_path = tmp_path / "terminated_progress.json"
    _write(
        terminated_path,
        status=StageStatus.SUCCEEDED,
        now_epoch_seconds=START_EPOCH_SECONDS + 5,
        terminal_entity_count=CANDIDATE_ENTITY_COUNT,
        running_entity_ids=(),
        last_heartbeat_epoch_seconds=START_EPOCH_SECONDS,
        last_terminal_entity_id="来源发现候选-179",
    )
    terminated = read_stage_liveness(terminated_path, now_epoch_seconds=silent_now)

    assert stale.kind is StageLivenessKind.STALE_WHILE_RUNNING
    assert terminated.kind is StageLivenessKind.TERMINATED_NO_FURTHER_HEARTBEAT
    assert stale.kind is not terminated.kind
    # 已终止不因静默时间被再判一次过期：状态本身就说明不会再心跳。
    assert terminated.status is StageStatus.SUCCEEDED
    assert terminated.silence_seconds > terminated.heartbeat_stale_after_seconds


def test_terminated_stage_preserves_the_last_heartbeat_fact(tmp_path):
    """GWT-002.t8：终止后最后一次心跳的事实仍可读，不被清零或覆盖为空。"""
    path = tmp_path / "auto_research_progress.json"
    last_beat = START_EPOCH_SECONDS + 3 * FROZEN_HEARTBEAT_INTERVAL_SECONDS
    _write(path, status=StageStatus.RUNNING, now_epoch_seconds=last_beat)
    before = read_stage_liveness(path, now_epoch_seconds=last_beat)

    terminated_at = last_beat + 7
    _write(
        path,
        status=StageStatus.INTERRUPTED,
        now_epoch_seconds=terminated_at,
        terminal_entity_count=42,
        running_entity_ids=(),
        last_heartbeat_epoch_seconds=before.last_heartbeat_epoch_seconds,
        last_terminal_entity_id="来源发现候选-041",
    )
    after = read_stage_liveness(path, now_epoch_seconds=terminated_at)

    assert after.kind is StageLivenessKind.TERMINATED_NO_FURTHER_HEARTBEAT
    assert after.last_heartbeat_epoch_seconds == before.last_heartbeat_epoch_seconds
    assert after.last_heartbeat_at == before.last_heartbeat_at
    assert after.last_heartbeat_at != ""
    assert after.terminal_entity_count == 42


def test_a_terminated_stage_must_carry_the_heartbeat_it_last_observed(tmp_path):
    """终止文档缺最后心跳事实时写入期判否，不允许落一份没有心跳事实的终态。"""
    path = tmp_path / "auto_research_progress.json"
    with pytest.raises(ValueError, match="last heartbeat"):
        _write(
            path,
            status=StageStatus.SUCCEEDED,
            now_epoch_seconds=START_EPOCH_SECONDS,
            running_entity_ids=(),
        )


def test_absent_unreadable_and_incomplete_progress_are_typed_failures(tmp_path):
    """GWT-002.t9：缺席/不可读/缺字段各自 typed 失败，不读成进度为零或默认存活。"""
    absent = read_stage_liveness(
        tmp_path / "never_written.json",
        now_epoch_seconds=START_EPOCH_SECONDS,
    )
    assert absent.kind is StageLivenessKind.PROGRESS_ABSENT
    assert absent.is_failure
    # 缺席不塌陷成「候选 0、终态 0」，也不默认判为存活。
    assert absent.candidate_entity_count is None
    assert absent.terminal_entity_count is None
    assert absent.status is None
    assert absent.kind is not StageLivenessKind.PROGRESSING

    unreadable = tmp_path / "unreadable_progress.json"
    unreadable.write_text("{ not json", encoding="utf-8")
    unreadable_reading = read_stage_liveness(
        unreadable,
        now_epoch_seconds=START_EPOCH_SECONDS,
    )
    assert unreadable_reading.kind is StageLivenessKind.PROGRESS_UNREADABLE
    assert unreadable_reading.terminal_entity_count is None

    incomplete = tmp_path / "incomplete_progress.json"
    complete_path = tmp_path / "complete_progress.json"
    _write(
        complete_path,
        status=StageStatus.RUNNING,
        now_epoch_seconds=START_EPOCH_SECONDS,
    )
    document = json.loads(complete_path.read_text(encoding="utf-8"))
    del document["lastHeartbeatEpochSeconds"]
    del document["heartbeatStaleAfterSeconds"]
    incomplete.write_text(json.dumps(document), encoding="utf-8")
    incomplete_reading = read_stage_liveness(
        incomplete,
        now_epoch_seconds=START_EPOCH_SECONDS,
    )
    assert (
        incomplete_reading.kind is StageLivenessKind.PROGRESS_REQUIRED_FIELD_MISSING
    )
    assert incomplete_reading.missing_fields == (
        "heartbeatStaleAfterSeconds",
        "lastHeartbeatEpochSeconds",
    )
    assert incomplete_reading.terminal_entity_count is None

    undeclared = tmp_path / "undeclared_status_progress.json"
    document = json.loads(complete_path.read_text(encoding="utf-8"))
    document["status"] = "healthy"
    undeclared.write_text(json.dumps(document), encoding="utf-8")
    undeclared_reading = read_stage_liveness(
        undeclared,
        now_epoch_seconds=START_EPOCH_SECONDS,
    )
    assert undeclared_reading.kind is StageLivenessKind.PROGRESS_STATUS_UNDECLARED
    assert undeclared_reading.undeclared_status == "healthy"
    assert undeclared_reading.is_failure


def test_a_previous_reading_never_impersonates_the_current_fact(tmp_path):
    """GWT-002.t9：读取面每次重新读盘，上一份快照不冒充当前事实。"""
    path = tmp_path / "auto_research_progress.json"
    _write(path, status=StageStatus.RUNNING, now_epoch_seconds=START_EPOCH_SECONDS)
    live = read_stage_liveness(path, now_epoch_seconds=START_EPOCH_SECONDS)
    assert live.kind is StageLivenessKind.PROGRESSING

    path.unlink()
    after_removal = read_stage_liveness(
        path,
        now_epoch_seconds=START_EPOCH_SECONDS + 1,
    )
    assert after_removal.kind is StageLivenessKind.PROGRESS_ABSENT
    assert after_removal.execution_id == ""


def test_heartbeat_run_facts_are_declared_single_run_observations(tmp_path):
    """GWT-002.t10：心跳里的耗时与速率自带本次运行事实声明位。"""
    path = tmp_path / "auto_research_progress.json"
    progress = _write(
        path,
        status=StageStatus.RUNNING,
        now_epoch_seconds=START_EPOCH_SECONDS + 60,
        terminal_entity_count=30,
    )

    assert progress["runFacts"]["factKind"] == SINGLE_RUN_OBSERVATION
    assert progress["runFacts"]["elapsedSeconds"] == 60.0
    assert progress["runFacts"]["entitiesPerMinute"] == 30.0
    assert set(progress["runFacts"]) == {
        "factKind",
        "elapsedSeconds",
        "entitiesPerMinute",
    }


def test_run_facts_never_reach_dispatch_admission_publish_or_milestone_paths():
    """GWT-002.t10：本次运行事实只被呈现，不参与任何判定分支。

    速率与耗时只在报告与进度面上被产出和透传；一旦有判定代码读它，这里就会失败。
    """
    scripts_root = Path(__file__).resolve()
    while scripts_root.name != "quwoquan_data":
        scripts_root = scripts_root.parent
    scripts_root = scripts_root / "scripts"

    # 只允许这几处出现，它们都是「产出或原样透传运行事实」的报告面。
    presentation_only = {
        "content/source/research/source_discovery_scheduler.py",
        "content/source/research/stage_liveness.py",
        "content/source/research/auto_plan_public.py",
        "content/execution/agent/auto_research.py",
        "content/execution/recovery/download_unresolved.py",
        "content/execution/controller/control.py",
    }
    offenders = sorted(
        path.relative_to(scripts_root).as_posix()
        for path in scripts_root.rglob("*.py")
        if "entitiesPerMinute" in path.read_text(encoding="utf-8")
        and path.relative_to(scripts_root).as_posix() not in presentation_only
    )

    assert offenders == []


def test_frozen_thresholds_must_keep_stale_after_above_the_interval(tmp_path):
    """过期阈值必须严格大于心跳间隔，否则写入期判否。"""
    path = tmp_path / "auto_research_progress.json"
    with pytest.raises(ValueError, match="staleAfter"):
        write_source_discovery_progress(
            EXECUTION_ID,
            status=StageStatus.RUNNING,
            candidate_entity_count=CANDIDATE_ENTITY_COUNT,
            terminal_entity_count=0,
            running_entity_ids=(),
            frozen_max_concurrent_workers=FROZEN_CEILING,
            heartbeat_interval_seconds=FROZEN_HEARTBEAT_INTERVAL_SECONDS,
            heartbeat_stale_after_seconds=FROZEN_HEARTBEAT_INTERVAL_SECONDS,
            elapsed_seconds=1.0,
            now_epoch_seconds=START_EPOCH_SECONDS,
            path=path,
        )
