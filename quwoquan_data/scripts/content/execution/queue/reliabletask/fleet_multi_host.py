"""Fail closed until a governed external multi-host executor is available."""
from __future__ import annotations

from collections.abc import Mapping

from core.control_types import QueueJobStage
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueError,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
)

from content.execution.identity import parse_execution_id
from content.execution.queue.reliabletask.report import ReliableTaskFleetReport


def run_multi_host_fleet(
    execution_id: str,
    stage: QueueJobStage,
) -> ReliableTaskFleetReport:
    from content.execution import store
    from content.execution.queue.reliabletask.fleet import (
        _run_reliabletask_host,
    )

    policy = store.load_spec(execution_id).get("executionPolicy") or {}
    binding = policy.get("workerHostSetBinding")
    if binding is None:
        return _run_reliabletask_host(execution_id, stage)
    if not isinstance(binding, Mapping):
        raise TypeError("governed fleet workerHostSetBinding is invalid")
    assignments = binding.get("hosts")
    host_ids = tuple(sorted(
        str(row.get("hostScopeId") or "")
        for row in assignments if isinstance(row, Mapping)
    )) if isinstance(assignments, list) else ()
    if not host_ids or any(not host_id for host_id in host_ids):
        raise ValueError("governed fleet has no assigned hosts")
    if len(host_ids) != 1:
        lane = DataIssueLane(parse_execution_id(execution_id).content_type.value)
        raise DataIssueError((DataIssue(
            code=DataIssueCode.REMOTE_HOST_EXECUTOR_UNAVAILABLE,
            stage=DataIssueStage(stage.value),
            lane=lane,
            ref=execution_id,
            recovery=DataRecoveryAction.STOP,
            message=(
                "governed multi-host ReliableTask requires an audited external "
                "host executor; local subprocesses cannot prove distinct hosts"
            ),
        ),))
    return _run_reliabletask_host(
        execution_id,
        stage,
        host_scope_id=host_ids[0],
    )


__all__ = ["run_multi_host_fleet"]
