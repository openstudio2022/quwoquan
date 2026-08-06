"""Fenced, restartable runtime journal for one four-lane content campaign.

The public campaign plan/report remain the release-facing contract.  This module
owns only disposable controller runtime facts: one compact snapshot, append-only
events, and one checkpoint per lane.  A new controller generation fences every
writer from a killed or stale predecessor before work is resumed.
"""

from __future__ import annotations

import fcntl
import os
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json, write_json
from core.runtime_policy import active_runtime_policy

from content.execution.campaign_runtime_process import (
    CampaignControllerTerminated,
    CampaignLeaseTakeoverError,
    append_runtime_event,
    begin_stale_controller_termination,
    campaign_controller_process_identity,
    campaign_snapshot_guard,
    controller_signal_guard,
    finish_stale_controller_termination,
    new_campaign_run_identity,
    reconcile_stale_generation,
    same_controller_identity,
    stale_takeover_candidate,
    terminate_lane_process,
)
from content.execution.campaign_submission import campaign_root
from content.execution.campaign_workspace import CampaignRuntimePaths
from content.execution.identity import validate_execution_id

RUNTIME_SNAPSHOT_SCHEMA = "quwoquan_data.content_campaign_runtime_snapshot"
RUNTIME_EVENT_SCHEMA = "quwoquan_data.content_campaign_runtime_event"
LANE_CHECKPOINT_SCHEMA = "quwoquan_data.content_campaign_lane_checkpoint"
_HEARTBEAT_THREAD_JOIN_TIMEOUT_SECONDS = active_runtime_policy().process_termination_timeout_seconds


class CampaignFenceError(RuntimeError):
    """A stale controller generation attempted to mutate current runtime state."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_root(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return (
        campaign_root(
            validate_execution_id(root_execution_id),
            root=runtime.campaigns_root,
        )
        / "runtime"
    )


def runtime_snapshot_path(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> Path:
    return runtime_root(runtime, root_execution_id) / "snapshot.json"


def runtime_events_path(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> Path:
    return runtime_root(runtime, root_execution_id) / "events.jsonl"


def lane_checkpoint_path(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    carrier: str,
) -> Path:
    return runtime_root(runtime, root_execution_id) / "lanes" / f"{carrier}.json"


def _runtime_snapshot_lock_path(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> Path:
    return runtime_root(runtime, root_execution_id) / ".snapshot.lock"


def _read_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError(f"campaign runtime document must be an object: {path}")
    return payload


def read_runtime_snapshot(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> dict[str, Any] | None:
    return _read_mapping(runtime_snapshot_path(runtime, root_execution_id))


def read_lane_checkpoint(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    carrier: str,
) -> dict[str, Any] | None:
    return _read_mapping(lane_checkpoint_path(runtime, root_execution_id, carrier))


def assert_campaign_fence(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    run_id: str,
    generation: int,
    fencing_token: str,
) -> dict[str, Any]:
    snapshot = read_runtime_snapshot(runtime, root_execution_id)
    if not snapshot:
        raise CampaignFenceError("campaign runtime snapshot is missing")
    if (
        str(snapshot.get("runId") or "") != str(run_id)
        or int(snapshot.get("generation") or 0) != int(generation)
        or str(snapshot.get("fencingToken") or "") != str(fencing_token)
    ):
        raise CampaignFenceError(
            "DATA.CAMPAIGN.FENCED stale controller generation "
            f"runId={run_id} generation={generation}"
        )
    return snapshot


@dataclass(slots=True)
class CampaignRunSession:
    runtime: CampaignRuntimePaths
    root_execution_id: str
    run_id: str
    generation: int
    fencing_token: str
    lease_seconds: int
    process_termination_timeout_seconds: float
    started_at: str
    _mutex: threading.RLock
    _stop: threading.Event
    _heartbeat_thread: threading.Thread | None = None
    _finished: bool = False

    def assert_fence(self) -> dict[str, Any]:
        return assert_campaign_fence(
            self.runtime,
            self.root_execution_id,
            run_id=self.run_id,
            generation=self.generation,
            fencing_token=self.fencing_token,
        )

    def _write_snapshot(self, **changes: object) -> dict[str, Any]:
        with self._mutex, campaign_snapshot_guard(
            _runtime_snapshot_lock_path(self.runtime, self.root_execution_id)
        ):
            snapshot = self.assert_fence()
            snapshot.update(changes)
            snapshot["heartbeatAt"] = _utc_now()
            snapshot["updatedAt"] = snapshot["heartbeatAt"]
            write_json(
                runtime_snapshot_path(self.runtime, self.root_execution_id),
                snapshot,
            )
            return snapshot

    def heartbeat(self) -> None:
        self._write_snapshot()

    def event(self, event_type: str, **attributes: object) -> None:
        with self._mutex, campaign_snapshot_guard(
            _runtime_snapshot_lock_path(self.runtime, self.root_execution_id)
        ):
            self.assert_fence()
            append_runtime_event(
                runtime_events_path(self.runtime, self.root_execution_id),
                {
                    "schema": RUNTIME_EVENT_SCHEMA,
                    "rootExecutionId": self.root_execution_id,
                    "runId": self.run_id,
                    "generation": self.generation,
                    "fencingToken": self.fencing_token,
                    "eventType": event_type,
                    "recordedAt": _utc_now(),
                    **attributes,
                },
            )

    def campaign_checkpoint(
        self,
        *,
        phase: str,
        status: str = "active",
        plan_digest: str | None = None,
    ) -> None:
        changes: dict[str, object] = {"phase": phase, "status": status}
        if plan_digest is not None:
            changes["planDigest"] = plan_digest
        self._write_snapshot(**changes)
        self.event(
            "campaign_checkpoint",
            phase=phase,
            status=status,
            planDigest=plan_digest,
        )

    def lane_checkpoint(
        self,
        *,
        carrier: str,
        execution_id: str,
        phase: str,
        status: str,
        capsule_ref: str,
        execution_root: Path,
        pid: int | None = None,
        pgid: int | None = None,
        return_code: int | None = None,
        error: str | None = None,
        termination: str | None = None,
    ) -> Path:
        with self._mutex:
            with campaign_snapshot_guard(
                _runtime_snapshot_lock_path(self.runtime, self.root_execution_id)
            ):
                self.assert_fence()
                path = lane_checkpoint_path(
                    self.runtime,
                    self.root_execution_id,
                    carrier,
                )
                previous = _read_mapping(path) or {}
                if previous and (
                    str(previous.get("runId") or "") != self.run_id
                    or int(previous.get("generation") or 0) != self.generation
                ):
                    previous = {}
                now = _utc_now()
                payload = {
                    "schema": LANE_CHECKPOINT_SCHEMA,
                    "rootExecutionId": self.root_execution_id,
                    "runId": self.run_id,
                    "generation": self.generation,
                    "fencingToken": self.fencing_token,
                    "carrier": carrier,
                    "executionId": execution_id,
                    "phase": phase,
                    "status": status,
                    "capsuleRef": capsule_ref,
                    "executionRoot": str(execution_root),
                    "pid": pid if pid is not None else previous.get("pid"),
                    "pgid": pgid if pgid is not None else previous.get("pgid"),
                    "returnCode": (
                        return_code
                        if return_code is not None
                        else previous.get("returnCode")
                    ),
                    "error": error,
                    "termination": termination,
                    "startedAt": str(previous.get("startedAt") or now),
                    "updatedAt": now,
                }
                write_json(path, payload)
                snapshot = self.assert_fence()
                lanes = dict(snapshot.get("lanes") or {})
                lanes[carrier] = {
                    "executionId": execution_id,
                    "phase": phase,
                    "status": status,
                    "pid": payload["pid"],
                    "pgid": payload["pgid"],
                    "returnCode": payload["returnCode"],
                    "updatedAt": now,
                }
                snapshot.update(
                    {"lanes": lanes, "heartbeatAt": now, "updatedAt": now}
                )
                write_json(
                    runtime_snapshot_path(self.runtime, self.root_execution_id),
                    snapshot,
                )
            self.event(
                "lane_checkpoint",
                carrier=carrier,
                executionId=execution_id,
                phase=phase,
                status=status,
                pid=payload["pid"],
                pgid=payload["pgid"],
                returnCode=payload["returnCode"],
                error=error,
            )
            return path

    def abort_active_lanes(self) -> None:
        for path in sorted(
            (runtime_root(self.runtime, self.root_execution_id) / "lanes").glob(
                "*.json"
            )
        ):
            checkpoint = _read_mapping(path)
            if not checkpoint:
                continue
            if (
                str(checkpoint.get("runId") or "") != self.run_id
                or int(checkpoint.get("generation") or 0) != self.generation
                or str(checkpoint.get("status") or "") not in {"starting", "running"}
            ):
                continue
            termination = terminate_lane_process(
                checkpoint,
                grace_seconds=self.process_termination_timeout_seconds,
            )
            self.lane_checkpoint(
                carrier=str(checkpoint.get("carrier") or path.stem),
                execution_id=str(checkpoint.get("executionId") or ""),
                phase=str(checkpoint.get("phase") or "unknown"),
                status="interrupted",
                capsule_ref=str(checkpoint.get("capsuleRef") or ""),
                execution_root=Path(str(checkpoint.get("executionRoot") or ".")),
                pid=int(checkpoint.get("pid") or 0) or None,
                pgid=int(checkpoint.get("pgid") or 0) or None,
                error="DATA.CAMPAIGN.CONTROLLER_INTERRUPTED",
                termination=termination,
            )

    def finish(self, *, status: str, phase: str, failure: str | None) -> None:
        if self._finished:
            return
        self._write_snapshot(
            status=status,
            phase=phase,
            failure=failure,
            finishedAt=_utc_now(),
        )
        self.event(
            "campaign_finished",
            status=status,
            phase=phase,
            failure=failure,
        )
        self._finished = True

    def _heartbeat_loop(self) -> None:
        interval = max(0.25, min(10.0, self.lease_seconds / 3.0))
        while not self._stop.wait(interval):
            try:
                self.heartbeat()
            except CampaignFenceError:
                return


@contextmanager
def campaign_run_session(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    lease_seconds: int,
    process_termination_timeout_seconds: float = _HEARTBEAT_THREAD_JOIN_TIMEOUT_SECONDS,
) -> Iterator[CampaignRunSession]:
    """Acquire one fenced generation, including identity-safe live-stall takeover."""
    if lease_seconds < 1:
        raise ValueError("campaign leaseSeconds must be positive")
    if process_termination_timeout_seconds <= 0:
        raise ValueError("campaign process termination timeout must be positive")
    root_id = validate_execution_id(root_execution_id)
    lock_path = campaign_root(root_id, root=runtime.campaigns_root) / ".controller.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        takeover_candidate: dict[str, Any] | None = None
        controller_termination: str | None = None
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            with campaign_snapshot_guard(
                _runtime_snapshot_lock_path(runtime, root_id),
                timeout_seconds=min(
                    max(process_termination_timeout_seconds, 0.25),
                    2.0,
                ),
            ):
                takeover_candidate = stale_takeover_candidate(
                    read_runtime_snapshot(runtime, root_id)
                )
                termination = begin_stale_controller_termination(
                    takeover_candidate,
                    root_execution_id=root_id,
                )
            controller_termination = finish_stale_controller_termination(
                termination,
                grace_seconds=process_termination_timeout_seconds,
            )
            lock_deadline = time.monotonic() + max(
                process_termination_timeout_seconds,
                1.0,
            )
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= lock_deadline:
                        raise CampaignLeaseTakeoverError(
                            "DATA.CAMPAIGN.TAKEOVER_LOCK_NOT_RELEASED",
                            f"stale controller lock remained active: {root_id}",
                        ) from exc
                    time.sleep(0.05)

        previous = read_runtime_snapshot(runtime, root_id)
        if takeover_candidate is not None and (
            previous is None
            or not same_controller_identity(takeover_candidate, previous)
        ):
            raise CampaignLeaseTakeoverError(
                "DATA.CAMPAIGN.TAKEOVER_IDENTITY_MISMATCH",
                "runtime identity changed after stale controller termination",
            )
        if previous and str(previous.get("status") or "") == "active":
            # The non-blocking flock above is the controller authority.  Once it
            # is acquired, an ``active`` snapshot can only belong to a killed or
            # lock-lost generation, even when its PID was rapidly reused.
            reconcile_stale_generation(
                runtime_root_path=runtime_root(runtime, root_id),
                snapshot_path=runtime_snapshot_path(runtime, root_id),
                events_path=runtime_events_path(runtime, root_id),
                root_execution_id=root_id,
                snapshot=previous,
                process_termination_timeout_seconds=(
                    process_termination_timeout_seconds
                ),
                controller_termination=controller_termination,
                event_schema=RUNTIME_EVENT_SCHEMA,
            )

        if takeover_candidate is not None:
            append_runtime_event(
                runtime_events_path(runtime, root_id),
                {
                    "schema": RUNTIME_EVENT_SCHEMA,
                    "rootExecutionId": root_id,
                    "runId": str(takeover_candidate["runId"]),
                    "generation": int(takeover_candidate["generation"]),
                    "fencingToken": str(takeover_candidate["fencingToken"]),
                    "eventType": "stale_controller_takeover",
                    "recordedAt": _utc_now(),
                    "controllerTermination": controller_termination,
                },
            )

        generation = int((previous or {}).get("generation") or 0) + 1
        run_id, token = new_campaign_run_identity(root_id, generation)
        now = _utc_now()
        pid = os.getpid()
        pgid = os.getpgrp()
        process_identity = campaign_controller_process_identity(
            root_id,
            run_id=run_id,
            generation=generation,
            fencing_token=token,
            pid=pid,
            pgid=pgid,
        )
        snapshot = {
            "schema": RUNTIME_SNAPSHOT_SCHEMA,
            "rootExecutionId": root_id,
            "runId": run_id,
            "generation": generation,
            "fencingToken": token,
            "status": "active",
            "phase": "submission",
            "planDigest": None,
            "pid": pid,
            "pgid": pgid,
            "hostname": socket.gethostname(),
            "controllerProcessIdentity": process_identity,
            "leaseSeconds": lease_seconds,
            "startedAt": now,
            "heartbeatAt": now,
            "updatedAt": now,
            "finishedAt": None,
            "failure": None,
            "lanes": {},
        }
        with campaign_snapshot_guard(_runtime_snapshot_lock_path(runtime, root_id)):
            write_json(runtime_snapshot_path(runtime, root_id), snapshot)
        append_runtime_event(
            runtime_events_path(runtime, root_id),
            {
                "schema": RUNTIME_EVENT_SCHEMA,
                "rootExecutionId": root_id,
                "runId": run_id,
                "generation": generation,
                "fencingToken": token,
                "eventType": "campaign_started",
                "recordedAt": now,
                "pid": pid,
                "pgid": pgid,
                "controllerProcessIdentity": process_identity,
                "recoveredGeneration": (
                    int(previous.get("generation") or 0) if previous else None
                ),
            },
        )
        session = CampaignRunSession(
            runtime=runtime,
            root_execution_id=root_id,
            run_id=run_id,
            generation=generation,
            fencing_token=token,
            lease_seconds=lease_seconds,
            process_termination_timeout_seconds=process_termination_timeout_seconds,
            started_at=now,
            _mutex=threading.RLock(),
            _stop=threading.Event(),
        )
        session._heartbeat_thread = threading.Thread(
            target=session._heartbeat_loop,
            name=f"campaign-heartbeat-{root_id}",
            daemon=True,
        )
        session._heartbeat_thread.start()
        try:
            with controller_signal_guard():
                yield session
        except BaseException as exc:
            cleanup_failure: str | None = None
            try:
                session.abort_active_lanes()
            except Exception as cleanup_exc:  # noqa: BLE001
                cleanup_failure = (
                    f"lane cleanup failed: {type(cleanup_exc).__name__}: "
                    f"{cleanup_exc}"
                )
            try:
                session.finish(
                    status="interrupted",
                    phase="controller",
                    failure="; ".join(
                        item
                        for item in (
                            f"{type(exc).__name__}: {exc}",
                            cleanup_failure,
                        )
                        if item
                    ),
                )
            except CampaignFenceError:
                pass
            raise
        finally:
            session._stop.set()
            if session._heartbeat_thread is not None:
                session._heartbeat_thread.join(
                    timeout=_HEARTBEAT_THREAD_JOIN_TIMEOUT_SECONDS
                )
            if not session._finished:
                try:
                    session.finish(
                        status="interrupted",
                        phase="controller",
                        failure="DATA.CAMPAIGN.CONTROLLER_EXITED_WITHOUT_TERMINAL_STATE",
                    )
                except CampaignFenceError:
                    pass
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = [
    "CampaignControllerTerminated",
    "CampaignFenceError",
    "CampaignLeaseTakeoverError",
    "CampaignRunSession",
    "assert_campaign_fence",
    "campaign_run_session",
    "lane_checkpoint_path",
    "read_lane_checkpoint",
    "read_runtime_snapshot",
    "runtime_events_path",
    "runtime_snapshot_path",
]
