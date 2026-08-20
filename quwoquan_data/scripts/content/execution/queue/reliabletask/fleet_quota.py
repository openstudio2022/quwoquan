"""Create-once fleet request naming and remaining-quota calculation."""

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


from content.execution.queue.reliabletask.fleet_recovery import (
    _has_audited_remote_recovery,
    _object_timeout_seconds,
)


def _attempt_request_name(*, recover_dead_tasks: bool) -> str:
    """Keep audited recovery input separate from the immutable first attempt."""

    return "recovery-request.json" if recover_dead_tasks else "request.json"


def _remaining_quota(
    execution_id: str,
    stage: QueueJobStage,
    active_job_count: int,
) -> int:
    """Remaining approved quota this fleet invocation must still deliver.

    The batch gate admits on quota, never on全量成功, so the request carries the
    quota that is still outstanding for this stage.  Objects already accepted in
    an earlier invocation are subtracted; the oversampled surplus is free to fail.
    """
    from content.execution import store

    policy = store.load_spec(execution_id).get("executionPolicy") or {}
    approved = policy.get("approvedQuota")
    if isinstance(approved, bool) or not isinstance(approved, int) or approved < 1:
        raise ValueError(
            f"execution {execution_id} executionPolicy.approvedQuota is required"
        )
    already_accepted = sum(
        1
        for job in _load_jobs(execution_id)
        if job.backend is QueueBackend.RELIABLE_TASK
        and job.stage is stage
        and job.state is QueueJobState.SUCCEEDED
    )
    remaining = approved - already_accepted
    if remaining < 1:
        raise ValueError(
            f"execution {execution_id} 已达 {stage.value} 准出配额 "
            f"{approved}（已接受 {already_accepted}），无需再派发 fleet"
        )
    if remaining > active_job_count and stage is not QueueJobStage.PUBLISH:
        raise ValueError(
            f"候选池耗尽，区域实体供给不足：{stage.value} 剩余配额 {remaining} "
            f"超过待执行 job 数 {active_job_count}"
        )
    # Publication consumes the immutable review-qualified closure.  The
    # semantic approvedQuota is a milestone target, not authority to suppress
    # already qualified objects when the reviewed closure is partial.  Deliver
    # every frozen publish job and leave the remaining milestone gap to a new
    # source/semantic wave; author acquisition remains strict above.
    return min(remaining, active_job_count)
