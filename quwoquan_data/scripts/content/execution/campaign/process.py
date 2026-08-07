"""Concurrent subprocess execution from one capsule into isolated lane roots."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.io import read_json

from content.execution.campaign.external_inputs import verify_external_input_refs
from content.execution.campaign.lane_process_result import (
    lane_process_evidence as _lane_process_evidence,
)
from content.execution.campaign.lane_process_result import (
    termination_owner as _termination_owner,
)
from content.execution.campaign.lane_process_result import (
    typed_execution_terminal_cause as _typed_execution_terminal_cause,
)
from content.execution.campaign.runtime_process import terminate_lane_process
from content.execution.campaign.submission import campaign_root
from content.execution.campaign.workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
)
from content.execution.queue.reliabletask.transport import (
    CAMPAIGN_ROOT_ENV,
    FLEET_BINDING_DIGEST_ENV,
    FLEET_MONGO_URI_ENV,
    FLEET_PLAN_DIGEST_ENV,
    FLEET_REDIS_ADDR_ENV,
    FLEET_TARGET_ENV,
    FrozenReliableTaskFleetBinding,
)
from content.execution.runtime_evidence.reliabletask_process import (
    OBSERVER_BINARY_REF_ENV,
    OBSERVER_BINARY_SHA256_ENV,
    ReliableTaskObserverBinaryBinding,
)

if TYPE_CHECKING:
    from content.execution.campaign.runtime import CampaignRunSession


CAMPAIGN_CARRIERS = ("homepage", "article", "image", "video")
LaneRunner = Callable[[list[str], Path, dict[str, str], Path, float], int]
PhaseResultCallback = Callable[[str, tuple[int, str | None]], None]
_LANE_SLICE_YIELD_CODE = 10
_LANE_PROCESS_SAMPLE_SECONDS = 5.0
_PROCESS_INSPECTION_TIMEOUT_SECONDS = 2


def _verify_workspace_external_inputs(workspace: CampaignLaneWorkspace) -> None:
    lane = workspace.capsule.lane_external_inputs[workspace.carrier]
    verify_external_input_refs(
        workspace.carrier,
        lane["externalInputRefs"],
        acquisition_root=workspace.capsule.external_input_root(workspace.carrier),
        source_revision=workspace.capsule.source_revision,
        source_digest=workspace.capsule.source_digest,
        entity_catalog_digest=workspace.capsule.entity_catalog_digest,
    )


def _lane_argv(submission: dict[str, Any], *, stage: str) -> list[str]:
    argv = [
        "task",
        "execute",
        "--execution-id",
        str(submission["executionId"]),
        "--campaign-root-execution-id",
        str(submission["rootExecutionId"]),
        "--family",
        str(submission["familyRef"]),
        "--region-ref",
        str(submission["regionRef"]),
        "--selector",
        str(submission["selector"]),
        "--quota",
        str(submission["quota"]),
        "--count",
        str(submission["count"]),
        "--stage",
        stage,
        "--semantic-selection-id",
        str(submission["semanticSelectionId"]),
    ]
    retry_of = str(submission.get("retryOf") or "").strip()
    if retry_of:
        argv.extend(["--retry-of", retry_of])
    semantic_preflight = submission.get("semanticPreflightReceipt")
    if isinstance(semantic_preflight, dict):
        argv.extend(
            [
                "--semantic-preflight-receipt",
                str(semantic_preflight["receiptRef"]),
            ]
        )
    topic = str(submission.get("topic") or "").strip()
    if topic:
        argv.extend(["--topic", topic])
    for provider in submission.get("sourceProviders") or []:
        argv.extend(["--source-provider", str(provider)])
    for name in submission.get("targetNames") or []:
        argv.extend(["--target", str(name)])
    return argv


def _process_group_rss_bytes(pgid: int) -> int:
    """Sample the exact lane process group without a shell."""

    observed = subprocess.run(
        ["ps", "-ax", "-o", "pgid=", "-o", "rss="],
        check=False,
        capture_output=True,
        text=True,
        timeout=_PROCESS_INSPECTION_TIMEOUT_SECONDS,
    )
    if observed.returncode != 0:
        return 0
    total_kib = 0
    for line in observed.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            row_pgid, rss_kib = (int(field) for field in fields)
        except ValueError:
            continue
        if row_pgid == pgid:
            total_kib += max(0, rss_kib)
    return total_kib * 1024


def _execution_heartbeat_at(execution_root: Path) -> str | None:
    path = execution_root / "_shared" / "execution_state.json"
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
    except (OSError, TypeError, ValueError):
        return None
    value = str((payload or {}).get("heartbeatAt") or "").strip()
    return value or None


def _execution_has_resumable_checkpoint(execution_root: Path) -> bool:
    path = execution_root / "_shared" / "execution_state.json"
    try:
        payload = read_json(path)
    except (OSError, TypeError, ValueError):
        return False
    if not isinstance(payload, Mapping):
        return False
    waiting_checkpoint = str(payload.get("waitingCheckpoint") or "").strip()
    if not waiting_checkpoint:
        return False
    if payload.get("status") == "waiting_agent":
        return payload.get("controllerYield") is None
    controller_yield = payload.get("controllerYield")
    return (
        payload.get("status") == "repairing"
        and isinstance(controller_yield, Mapping)
        and controller_yield.get("stage") == waiting_checkpoint
    )


def _campaign_plan_digest(run_session: Any) -> str:
    value = str(getattr(run_session, "plan_digest", "") or "").strip()
    if value:
        return value
    assert_fence = getattr(run_session, "assert_fence", None)
    if callable(assert_fence):
        snapshot = assert_fence()
        value = str((snapshot or {}).get("planDigest") or "").strip()
    if not value:
        raise ValueError("campaign run session has no frozen plan digest")
    return value


def _default_lane_runner(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    timeout_seconds: float,
    *,
    run_session: CampaignRunSession,
    workspace: CampaignLaneWorkspace,
    execution_id: str,
    stage: str,
) -> int:
    started = time.monotonic()
    slice_count = 0
    max_rss_bytes = 0
    last_execution_heartbeat_at: str | None = None
    with log_path.open("w", encoding="utf-8") as log:
        while True:
            elapsed = time.monotonic() - started
            remaining = timeout_seconds - elapsed
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout_seconds)
            proc = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            slice_count += 1
            pgid = os.getpgid(proc.pid)
            run_session.lane_checkpoint(
                carrier=workspace.carrier,
                execution_id=execution_id,
                phase=stage,
                status="running",
                capsule_ref=workspace.ref,
                execution_root=workspace.execution_root,
                pid=proc.pid,
                pgid=pgid,
                process_evidence=_lane_process_evidence(
                    slice_count=slice_count,
                    elapsed_seconds=elapsed,
                    max_rss_bytes=max_rss_bytes,
                    heartbeat_at=last_execution_heartbeat_at,
                ),
            )
            try:
                while True:
                    elapsed = time.monotonic() - started
                    remaining = timeout_seconds - elapsed
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, timeout_seconds)
                    try:
                        code = int(
                            proc.wait(
                                timeout=min(_LANE_PROCESS_SAMPLE_SECONDS, remaining)
                            )
                        )
                        break
                    except subprocess.TimeoutExpired:
                        max_rss_bytes = max(
                            max_rss_bytes,
                            _process_group_rss_bytes(pgid),
                        )
                        last_execution_heartbeat_at = (
                            _execution_heartbeat_at(workspace.execution_root)
                            or last_execution_heartbeat_at
                        )
                        run_session.lane_checkpoint(
                            carrier=workspace.carrier,
                            execution_id=execution_id,
                            phase=stage,
                            status="running",
                            capsule_ref=workspace.ref,
                            execution_root=workspace.execution_root,
                            pid=proc.pid,
                            pgid=pgid,
                            process_evidence=_lane_process_evidence(
                                slice_count=slice_count,
                                elapsed_seconds=elapsed,
                                max_rss_bytes=max_rss_bytes,
                                heartbeat_at=last_execution_heartbeat_at,
                            ),
                        )
            except subprocess.TimeoutExpired:
                terminate_lane_process(
                    {
                        "pid": proc.pid,
                        "pgid": pgid,
                        "executionId": execution_id,
                    },
                    grace_seconds=run_session.process_termination_timeout_seconds,
                )
                proc.wait()
                run_session.lane_checkpoint(
                    carrier=workspace.carrier,
                    execution_id=execution_id,
                    phase=stage,
                    status="timed_out",
                    capsule_ref=workspace.ref,
                    execution_root=workspace.execution_root,
                    pid=proc.pid,
                    pgid=pgid,
                    return_code=124,
                    process_evidence=_lane_process_evidence(
                        slice_count=slice_count,
                        elapsed_seconds=time.monotonic() - started,
                        max_rss_bytes=max_rss_bytes,
                        heartbeat_at=last_execution_heartbeat_at,
                        owner="campaign_controller_timeout",
                    ),
                )
                raise
            elapsed = time.monotonic() - started
            max_rss_bytes = max(max_rss_bytes, _process_group_rss_bytes(pgid))
            last_execution_heartbeat_at = (
                _execution_heartbeat_at(workspace.execution_root)
                or last_execution_heartbeat_at
            )
            owner, signal_name = _termination_owner(code)
            resumable_checkpoint = (
                code == _LANE_SLICE_YIELD_CODE
                and _execution_has_resumable_checkpoint(workspace.execution_root)
            )
            run_session.lane_checkpoint(
                carrier=workspace.carrier,
                execution_id=execution_id,
                phase=stage,
                status="running",
                capsule_ref=workspace.ref,
                execution_root=workspace.execution_root,
                pid=proc.pid,
                pgid=pgid,
                return_code=code,
                process_evidence=_lane_process_evidence(
                    slice_count=slice_count,
                    elapsed_seconds=elapsed,
                    max_rss_bytes=max_rss_bytes,
                    heartbeat_at=last_execution_heartbeat_at,
                    owner=(
                        "controller_yield"
                        if resumable_checkpoint
                        else owner
                    ),
                    signal_name=signal_name,
                ),
            )
            if not resumable_checkpoint:
                return code
            log.write(
                "\n[content campaign] resuming create-once lane checkpoint "
                f"slice={slice_count + 1}\n"
            )
            log.flush()


def _run_lane(
    workspace: CampaignLaneWorkspace,
    submission: dict[str, Any],
    *,
    stage: str,
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    timeout_seconds: float,
    lane_runner: LaneRunner | None,
    run_session: CampaignRunSession,
    observer_binary_binding: ReliableTaskObserverBinaryBinding | None,
    fleet_transport_binding: FrozenReliableTaskFleetBinding | None,
) -> tuple[int, str | None]:
    log_path = (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "logs"
        / f"{workspace.carrier}-{stage}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cli = workspace.path / "quwoquan_data" / "scripts" / "cli.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    # A lane may only select the controller-frozen data-content-worker below;
    # never inherit an arbitrary fleet executable from the parent shell.
    env.pop("QWQ_DATA_FLEET_BINARY", None)
    env.pop(OBSERVER_BINARY_REF_ENV, None)
    env.pop(OBSERVER_BINARY_SHA256_ENV, None)
    for name in (
        FLEET_TARGET_ENV,
        FLEET_MONGO_URI_ENV,
        FLEET_REDIS_ADDR_ENV,
        FLEET_PLAN_DIGEST_ENV,
        FLEET_BINDING_DIGEST_ENV,
    ):
        env.pop(name, None)
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "QWQ_OUTPUT_ROOT": str(runtime.output_root),
            "QWQ_PUBLISH_ROOT": str(runtime.publish_root),
            CAMPAIGN_ROOT_ENV: root_execution_id,
            "QWQ_FROZEN_MAIN_BRANCH": str(submission["gitBranch"]),
            "QWQ_FROZEN_MAIN_COMMIT": str(submission["gitCommitSha"]),
            "QWQ_FROZEN_SOURCE_DIGEST": str(
                (submission.get("sourceDigest") or {}).get("digest") or ""
            ),
            "QWQ_CAMPAIGN_RUN_ID": run_session.run_id,
            "QWQ_CAMPAIGN_GENERATION": str(run_session.generation),
            "QWQ_CAMPAIGN_FENCING_TOKEN": run_session.fencing_token,
            "QWQ_CAMPAIGN_CARRIER": workspace.carrier,
            "QWQ_CAMPAIGN_EXECUTION_ID": str(submission["executionId"]),
            "QWQ_CAMPAIGN_PLAN_DIGEST": _campaign_plan_digest(run_session),
            "QWQ_CAMPAIGN_SOURCE_REVISION": str(
                submission.get("sourceRevision") or ""
            ),
            "QWQ_CAMPAIGN_ENTITY_CATALOG_DIGEST": str(
                submission.get("entityCatalogDigest") or ""
            ),
        }
    )
    if observer_binary_binding is not None:
        env.update(
            {
                OBSERVER_BINARY_REF_ENV: observer_binary_binding.ref,
                OBSERVER_BINARY_SHA256_ENV: observer_binary_binding.sha256,
            }
        )
    if fleet_transport_binding is not None:
        if fleet_transport_binding.root_execution_id != root_execution_id:
            raise ValueError("campaign fleet transport root execution drift")
        env.update(fleet_transport_binding.environment())
    command = [sys.executable, "-B", str(cli), *_lane_argv(submission, stage=stage)]
    execution_id = str(submission["executionId"])
    _verify_workspace_external_inputs(workspace)
    run_session.lane_checkpoint(
        carrier=workspace.carrier,
        execution_id=execution_id,
        phase=stage,
        status="starting",
        capsule_ref=workspace.ref,
        execution_root=workspace.execution_root,
    )
    try:
        if lane_runner is None:
            code = _default_lane_runner(
                command,
                workspace.execution_root,
                env,
                log_path,
                timeout_seconds,
                run_session=run_session,
                workspace=workspace,
                execution_id=execution_id,
                stage=stage,
            )
        else:
            run_session.lane_checkpoint(
                carrier=workspace.carrier,
                execution_id=execution_id,
                phase=stage,
                status="running",
                capsule_ref=workspace.ref,
                execution_root=workspace.execution_root,
                pid=os.getpid(),
                pgid=os.getpgrp(),
            )
            code = lane_runner(
                command,
                workspace.execution_root,
                env,
                log_path,
                timeout_seconds,
            )
        _verify_workspace_external_inputs(workspace)
        failure_detail: str | None = None
        if code != 0:
            failure_detail = _typed_execution_terminal_cause(
                workspace.execution_root,
                execution_id=execution_id,
            )
            if failure_detail is None:
                try:
                    lines = log_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    ).splitlines()
                except OSError:
                    lines = []
                excerpt = "\n".join(lines[-12:]).strip()
                failure_detail = (
                    excerpt[-2400:]
                    if excerpt
                    else f"{stage} exited with code {code}"
                )
        run_session.lane_checkpoint(
            carrier=workspace.carrier,
            execution_id=execution_id,
            phase=stage,
            status="succeeded" if code == 0 else "failed",
            capsule_ref=workspace.ref,
            execution_root=workspace.execution_root,
            return_code=int(code),
            error=failure_detail,
        )
        if code == 0:
            return 0, None
        return int(code), failure_detail
    except subprocess.TimeoutExpired:
        run_session.lane_checkpoint(
            carrier=workspace.carrier,
            execution_id=execution_id,
            phase=stage,
            status="timed_out",
            capsule_ref=workspace.ref,
            execution_root=workspace.execution_root,
            return_code=124,
            error=f"{stage} timed out after {timeout_seconds}s",
        )
        return 124, f"{stage} timed out after {timeout_seconds}s"
    except Exception as exc:  # noqa: BLE001
        run_session.lane_checkpoint(
            carrier=workspace.carrier,
            execution_id=execution_id,
            phase=stage,
            status="failed",
            capsule_ref=workspace.ref,
            execution_root=workspace.execution_root,
            return_code=2,
            error=f"{type(exc).__name__}: {exc}",
        )
        return 2, f"{type(exc).__name__}: {exc}"


def run_phase(
    workspaces: dict[str, CampaignLaneWorkspace],
    submissions: dict[str, dict[str, Any]],
    *,
    stage: str,
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    timeout_seconds: float,
    worker_count: int,
    lane_runner: LaneRunner | None = None,
    run_session: CampaignRunSession,
    observer_binary_binding: ReliableTaskObserverBinaryBinding | None = None,
    fleet_transport_binding: FrozenReliableTaskFleetBinding | None = None,
    carriers: tuple[str, ...] | None = None,
    on_result: PhaseResultCallback | None = None,
) -> dict[str, tuple[int, str | None]]:
    selected = CAMPAIGN_CARRIERS if carriers is None else carriers
    unknown = [carrier for carrier in selected if carrier not in CAMPAIGN_CARRIERS]
    if unknown:
        raise ValueError(f"campaign phase carriers are invalid: {', '.join(unknown)}")
    results: dict[str, tuple[int, str | None]] = {}
    if not selected:
        return results
    pool = ThreadPoolExecutor(max_workers=max(1, min(worker_count, len(selected))))
    futures = {}
    try:
        futures = {
            pool.submit(
                _run_lane,
                workspaces[carrier],
                submissions[carrier],
                stage=stage,
                runtime=runtime,
                root_execution_id=root_execution_id,
                timeout_seconds=timeout_seconds,
                lane_runner=lane_runner,
                run_session=run_session,
                observer_binary_binding=observer_binary_binding,
                fleet_transport_binding=fleet_transport_binding,
            ): carrier
            for carrier in selected
        }
        for future in as_completed(futures):
            carrier = futures[future]
            result = future.result()
            results[carrier] = result
            if on_result is not None:
                on_result(carrier, result)
    except BaseException:
        # A controller interrupt must first stop every owned process group;
        # otherwise ThreadPoolExecutor.__exit__ waits for the full lane timeout.
        run_session.abort_active_lanes()
        for future in futures:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    return results


__all__ = [
    "CAMPAIGN_CARRIERS",
    "LaneRunner",
    "PhaseResultCallback",
    "run_phase",
]
