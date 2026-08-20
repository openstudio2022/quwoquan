"""Audited recovery admission and timeout policy for ReliableTask fleets."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.control_types import QueueBackend, QueueJobStage, QueueJobState
from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REPO_ROOT
from core.python_environment import resolve_data_agent_python
from core.schema import assert_valid
from governance.coverage.distribution import (
    ProductLifecycleState,
    load_content_distribution_policy,
)

from content.execution.queue.backend import load_execution_queue_backend
from content.execution.queue.core import _load_jobs
from content.execution.queue.reliabletask.attempt import (
    attempt_evidence_dir,
    select_or_freeze_job_set_attempt,
    write_attempt_document_create_once,
)
from content.execution.queue.reliabletask.fleet_host_binding import (
    allocate_worker_host_quotas,
    fleet_job_document,
    require_fleet_carrier,
    select_worker_host_slice,
)
from content.execution.queue.reliabletask.report import ReliableTaskFleetReport
from content.execution.queue.reliabletask.transport import (
    ReliableTaskFleetTransport,
    _wait_for_fleet_transport,
    reliabletask_fleet_preflight,
    resolve_reliabletask_fleet_transport,
)
from content.execution.runtime_contract import canonical_sha256
from content.execution.runtime_evidence.reliabletask_process import (
    OBSERVER_BINARY_REF_ENV,
    OBSERVER_BINARY_SHA256_ENV,
    load_frozen_campaign_worker_binary_binding,
    load_frozen_observer_binary_binding,
    validate_frozen_observer_binary,
)

_RECOVERY_EXECUTION_STAGES_BY_QUEUE_STAGE = {
    QueueJobStage.AUTHOR: frozenset({"build_homepage", "post_author"}),
    QueueJobStage.PUBLISH: frozenset({"publish"}),
}


def _has_audited_remote_recovery(
    execution_id: str,
    stage: QueueJobStage,
) -> bool:
    """Permit DLQ revival only after the controller recorded recovery evidence."""
    from content.execution.support import load_execution_state

    accepted_stages = _RECOVERY_EXECUTION_STAGES_BY_QUEUE_STAGE.get(
        stage,
        frozenset({stage.value}),
    )
    state = load_execution_state(execution_id)
    for action in reversed(tuple(state.recovery_actions or ())):
        if not isinstance(action, Mapping):
            continue
        if str(action.get("stage") or "").strip() not in accepted_stages:
            continue
        if str(action.get("recoveredAt") or "").strip():
            return True
    return False


def _object_timeout_seconds(jobs: list[object]) -> int:
    from content.execution.queue.model import QueueJob

    if not jobs or not all(isinstance(job, QueueJob) for job in jobs):
        raise ValueError("ReliableTask fleet requires declared QueueJob values")
    values = {job.max_wall_clock_seconds for job in jobs}
    if len(values) != 1:
        raise ValueError("ReliableTask fleet jobs must share one object timeout")
    timeout_seconds = next(iter(values))
    if timeout_seconds < 1:
        raise ValueError("ReliableTask object timeout must be positive")
    return timeout_seconds
