"""来源发现阶段存活与进度的统一进度面：写入面与 typed 读取面。

`REQ-002` 要求阶段在尚未终止时可判定存活与进度，且该判定不读取连接数、CPU
占用、进程表、文件 mtime 猜测与日志尾部。本模块就是那一个进度面：写入侧按冻结的
心跳间隔持续落盘，读取侧只凭该文件返回 typed 结果。

读取结果是一个闭集，七个成员各自独立：仍在推进、运行中未按间隔心跳、已终止不会再
心跳，以及进度缺席、不可读、缺必需字段、阶段状态未声明这四种 typed 失败。任何失败都
不塌陷为进度为零，也不默认判为存活。读取面每次都重新读盘，上一份快照不会冒充当前事实。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from core.io import write_json
from core.paths import execution_root
from core.schema import assert_valid

STAGE_ID = "source_discovery"
PROGRESS_FILE_NAME = "auto_research_progress.json"
SINGLE_RUN_OBSERVATION = "single_run_observation"

_REQUIRED_INTEGER_FIELDS = (
    "lastHeartbeatEpochSeconds",
    "heartbeatIntervalSeconds",
    "heartbeatStaleAfterSeconds",
    "candidateEntityCount",
    "terminalEntityCount",
    "frozenMaxConcurrentWorkers",
)
_REQUIRED_STRING_FIELDS = ("executionId", "stageId", "status", "lastHeartbeatAt")


class StageStatus(str, Enum):
    """阶段是否还可能再心跳。"""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    INTERRUPTED = "interrupted"

    @property
    def is_terminated(self) -> bool:
        return self is not StageStatus.RUNNING


class StageLivenessKind(str, Enum):
    """存活读取结果闭集。"""

    PROGRESSING = "progressing"
    STALE_WHILE_RUNNING = "stale_while_running"
    TERMINATED_NO_FURTHER_HEARTBEAT = "terminated_no_further_heartbeat"
    PROGRESS_ABSENT = "progress_absent"
    PROGRESS_UNREADABLE = "progress_unreadable"
    PROGRESS_REQUIRED_FIELD_MISSING = "progress_required_field_missing"
    # 进度面写下了本端未声明的阶段状态：既不是失败的同义词，也不等价于任何放行态。
    PROGRESS_STATUS_UNDECLARED = "progress_status_undeclared"


FAILURE_KINDS = frozenset(
    {
        StageLivenessKind.PROGRESS_ABSENT,
        StageLivenessKind.PROGRESS_UNREADABLE,
        StageLivenessKind.PROGRESS_REQUIRED_FIELD_MISSING,
        StageLivenessKind.PROGRESS_STATUS_UNDECLARED,
    }
)


@dataclass(frozen=True, slots=True)
class StageLivenessReading:
    """一次存活读取。失败结果不携带进度数字，缺席就是缺席，不补零。"""

    kind: StageLivenessKind
    execution_id: str = ""
    status: StageStatus | None = None
    candidate_entity_count: int | None = None
    terminal_entity_count: int | None = None
    running_entity_ids: tuple[str, ...] = ()
    last_heartbeat_epoch_seconds: int | None = None
    last_heartbeat_at: str = ""
    heartbeat_interval_seconds: int | None = None
    heartbeat_stale_after_seconds: int | None = None
    silence_seconds: int | None = None
    missing_fields: tuple[str, ...] = ()
    undeclared_status: str = ""

    @property
    def is_failure(self) -> bool:
        return self.kind in FAILURE_KINDS


def stage_progress_path(execution_id: str) -> Path:
    return execution_root(execution_id) / "_shared" / PROGRESS_FILE_NAME


def _iso(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def write_source_discovery_progress(
    execution_id: str,
    *,
    status: StageStatus,
    candidate_entity_count: int,
    terminal_entity_count: int,
    running_entity_ids: Sequence[str],
    frozen_max_concurrent_workers: int,
    heartbeat_interval_seconds: int,
    heartbeat_stale_after_seconds: int,
    elapsed_seconds: float,
    now_epoch_seconds: int,
    last_heartbeat_epoch_seconds: int | None = None,
    last_terminal_entity_id: str = "",
    message: str = "",
    path: Path | None = None,
) -> dict[str, Any]:
    """写一次进度面。

    运行中的每一次写入就是一次心跳，心跳时刻即写入时刻；阶段终止时由调用方传入
    终止前最后一次心跳的时刻，使该事实在终态文档里仍可读。
    """
    if heartbeat_stale_after_seconds <= heartbeat_interval_seconds:
        raise ValueError(
            "frozen heartbeat staleAfter must be strictly greater than the "
            "frozen heartbeat interval"
        )
    if status is StageStatus.RUNNING:
        heartbeat_epoch = now_epoch_seconds
    elif last_heartbeat_epoch_seconds is None:
        raise ValueError(
            "a terminated source discovery stage must carry the last heartbeat "
            "instant observed before termination"
        )
    else:
        heartbeat_epoch = last_heartbeat_epoch_seconds
    elapsed = max(float(elapsed_seconds), 0.0)
    progress: dict[str, Any] = {
        "schema": "quwoquan.content.source.auto_research_progress",
        "executionId": execution_id,
        "stageId": STAGE_ID,
        "status": status.value,
        "updatedAt": _iso(now_epoch_seconds),
        "lastHeartbeatAt": _iso(heartbeat_epoch),
        "lastHeartbeatEpochSeconds": heartbeat_epoch,
        "heartbeatIntervalSeconds": heartbeat_interval_seconds,
        "heartbeatStaleAfterSeconds": heartbeat_stale_after_seconds,
        "candidateEntityCount": candidate_entity_count,
        "terminalEntityCount": terminal_entity_count,
        "runningEntityIds": [str(entity_id) for entity_id in running_entity_ids],
        "frozenMaxConcurrentWorkers": frozen_max_concurrent_workers,
        "runFacts": {
            # 声明位在字段里：这两个数只是本次运行事实，不是稳态吞吐或容量结论。
            "factKind": SINGLE_RUN_OBSERVATION,
            "elapsedSeconds": round(elapsed, 3),
            "entitiesPerMinute": (
                round(terminal_entity_count / elapsed * 60.0, 3) if elapsed > 0 else 0.0
            ),
        },
        "message": message,
    }
    if last_terminal_entity_id:
        progress["lastTerminalEntityId"] = last_terminal_entity_id
    assert_valid(
        progress,
        "source",
        "source_discovery_stage_progress",
        label="source discovery stage progress",
    )
    write_json(path or stage_progress_path(execution_id), progress)
    return progress


def _integer(payload: dict[str, Any], field: str) -> int | None:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def read_stage_liveness(
    path: Path,
    *,
    now_epoch_seconds: int,
) -> StageLivenessReading:
    """只凭进度面判定存活。每次调用都重新读盘，不缓存上一份快照。"""
    if path.is_symlink() or not path.is_file():
        return StageLivenessReading(kind=StageLivenessKind.PROGRESS_ABSENT)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return StageLivenessReading(kind=StageLivenessKind.PROGRESS_UNREADABLE)
    if not isinstance(payload, dict):
        return StageLivenessReading(kind=StageLivenessKind.PROGRESS_UNREADABLE)
    missing = [
        field
        for field in _REQUIRED_STRING_FIELDS
        if not isinstance(payload.get(field), str) or not payload.get(field)
    ]
    missing.extend(
        field for field in _REQUIRED_INTEGER_FIELDS if _integer(payload, field) is None
    )
    running = payload.get("runningEntityIds")
    if not isinstance(running, list) or any(
        not isinstance(entity_id, str) or not entity_id for entity_id in running
    ):
        missing.append("runningEntityIds")
    if missing:
        return StageLivenessReading(
            kind=StageLivenessKind.PROGRESS_REQUIRED_FIELD_MISSING,
            missing_fields=tuple(sorted(missing)),
        )
    declared_status = str(payload["status"])
    try:
        status = StageStatus(declared_status)
    except ValueError:
        return StageLivenessReading(
            kind=StageLivenessKind.PROGRESS_STATUS_UNDECLARED,
            undeclared_status=declared_status,
        )
    heartbeat_epoch = int(payload["lastHeartbeatEpochSeconds"])
    facts = {
        "execution_id": str(payload["executionId"]),
        "status": status,
        "candidate_entity_count": int(payload["candidateEntityCount"]),
        "terminal_entity_count": int(payload["terminalEntityCount"]),
        "running_entity_ids": tuple(str(entity_id) for entity_id in running),
        "last_heartbeat_epoch_seconds": heartbeat_epoch,
        "last_heartbeat_at": str(payload["lastHeartbeatAt"]),
        "heartbeat_interval_seconds": int(payload["heartbeatIntervalSeconds"]),
        "heartbeat_stale_after_seconds": int(payload["heartbeatStaleAfterSeconds"]),
        "silence_seconds": now_epoch_seconds - heartbeat_epoch,
    }
    if status.is_terminated:
        return StageLivenessReading(
            kind=StageLivenessKind.TERMINATED_NO_FURTHER_HEARTBEAT,
            **facts,
        )
    if facts["silence_seconds"] > int(payload["heartbeatStaleAfterSeconds"]):
        return StageLivenessReading(
            kind=StageLivenessKind.STALE_WHILE_RUNNING,
            **facts,
        )
    return StageLivenessReading(kind=StageLivenessKind.PROGRESSING, **facts)


__all__ = [
    "FAILURE_KINDS",
    "PROGRESS_FILE_NAME",
    "SINGLE_RUN_OBSERVATION",
    "STAGE_ID",
    "StageLivenessKind",
    "StageLivenessReading",
    "StageStatus",
    "read_stage_liveness",
    "stage_progress_path",
    "write_source_discovery_progress",
]
