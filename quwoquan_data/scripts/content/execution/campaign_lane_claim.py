"""Exclusive carrier claim for independently running campaign sessions."""
from __future__ import annotations

import fcntl
import hashlib
import os
import socket
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign_process import CAMPAIGN_CARRIERS
from content.execution.campaign_runtime_process import (
    controller_signal_guard,
    terminate_lane_process,
)
from content.execution.campaign_submission import campaign_root
from core.runtime_policy import active_runtime_policy
from content.execution.campaign_workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
)


_HEARTBEAT_THREAD_JOIN_TIMEOUT_SECONDS = (
    active_runtime_policy().process_termination_timeout_seconds
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lane_claim_path(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    carrier: str,
) -> Path:
    if carrier not in CAMPAIGN_CARRIERS:
        raise ValueError(f"campaign carrier is invalid: {carrier}")
    return (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "claims"
        / f"{carrier}.json"
    )


def read_lane_claim(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    carrier: str,
) -> dict[str, Any] | None:
    path = lane_claim_path(runtime, root_execution_id, carrier)
    if not path.is_file():
        return None
    payload = read_json(path)
    assert_valid(
        payload,
        "execution",
        "content_campaign_lane_claim",
        label=f"campaign lane claim:{carrier}",
    )
    return payload


def _claim_identity(
    root_execution_id: str,
    carrier: str,
    claim_attempt: int,
) -> str:
    seed = (
        f"{root_execution_id}|{carrier}|{claim_attempt}|{os.getpid()}|"
        f"{socket.gethostname()}|{time.monotonic_ns()}|{_utc_now()}"
    )
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class DistributedLaneSession:
    runtime: CampaignRuntimePaths
    root_execution_id: str
    carrier: str
    execution_id: str
    plan_digest: str
    run_id: str
    generation: int
    fencing_token: str
    claim_id: str
    claim_attempt: int
    workspace: CampaignLaneWorkspace
    process_termination_timeout_seconds: float
    _mutex: threading.RLock
    _stop: threading.Event
    _heartbeat_thread: threading.Thread | None = None
    _finished: bool = False

    @property
    def path(self) -> Path:
        return lane_claim_path(
            self.runtime,
            self.root_execution_id,
            self.carrier,
        )

    def _write(self, **changes: object) -> dict[str, Any]:
        with self._mutex:
            previous = read_json(self.path) if self.path.is_file() else {}
            if previous and (
                previous.get("claimId") != self.claim_id
                or previous.get("planDigest") != self.plan_digest
            ):
                raise RuntimeError(
                    f"DATA.CAMPAIGN.LANE_FENCED carrier={self.carrier}"
                )
            now = _utc_now()
            payload = {
                "schema": "quwoquan_data.content_campaign_lane_claim",
                "rootExecutionId": self.root_execution_id,
                "planDigest": self.plan_digest,
                "campaignRunId": self.run_id,
                "campaignGeneration": self.generation,
                "campaignFencingToken": self.fencing_token,
                "carrier": self.carrier,
                "executionId": self.execution_id,
                "claimId": self.claim_id,
                "claimAttempt": self.claim_attempt,
                "status": str(previous.get("status") or "active"),
                "phase": str(previous.get("phase") or "claim"),
                "capsuleRef": self.workspace.ref,
                "executionRoot": str(self.workspace.execution_root),
                "pid": previous.get("pid"),
                "pgid": previous.get("pgid"),
                "returnCode": previous.get("returnCode"),
                "error": previous.get("error"),
                "acquiredAt": str(previous.get("acquiredAt") or now),
                "heartbeatAt": now,
                "updatedAt": now,
                "finishedAt": previous.get("finishedAt"),
            }
            payload.update(changes)
            assert_valid(
                payload,
                "execution",
                "content_campaign_lane_claim",
                label=f"campaign lane claim:{self.carrier}",
            )
            write_json(self.path, payload)
            return payload

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
        if (
            carrier != self.carrier
            or execution_id != self.execution_id
            or capsule_ref != self.workspace.ref
            or execution_root.resolve() != self.workspace.execution_root.resolve()
            or termination is not None
        ):
            raise ValueError("distributed campaign lane checkpoint binding drift")
        self._write(
            phase=phase,
            status=status,
            pid=pid,
            pgid=pgid,
            returnCode=return_code,
            error=error,
        )
        return self.path

    def abort_active_lanes(self) -> None:
        claim = read_lane_claim(
            self.runtime,
            self.root_execution_id,
            self.carrier,
        )
        if not claim or claim.get("claimId") != self.claim_id:
            return
        termination = terminate_lane_process(
            claim,
            grace_seconds=self.process_termination_timeout_seconds,
        )
        self._write(
            status="interrupted",
            error=f"DATA.CAMPAIGN.LANE_INTERRUPTED termination={termination}",
            finishedAt=_utc_now(),
        )

    def finish(self, *, status: str, error: str | None = None) -> None:
        if self._finished:
            return
        self._write(
            status=status,
            phase="completed",
            error=error,
            finishedAt=_utc_now(),
        )
        self._finished = True

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(10.0):
            try:
                self._write()
            except RuntimeError:
                return


def _distributed_identity(plan: Mapping[str, Any]) -> tuple[str, int, str]:
    if plan.get("executionMode") != "distributed":
        raise ValueError("campaign-lane-run requires a distributed campaign plan")
    binding = plan.get("distributedRun")
    if not isinstance(binding, Mapping):
        raise ValueError("distributed campaign run binding is missing")
    run_id = str(binding.get("campaignRunId") or "")
    generation = int(binding.get("campaignGeneration") or 0)
    token = str(binding.get("campaignFencingToken") or "")
    if not run_id or generation < 1 or not token.startswith("sha256:"):
        raise ValueError("distributed campaign run binding is invalid")
    return run_id, generation, token


@contextmanager
def campaign_lane_claim_session(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    plan: Mapping[str, Any],
    carrier: str,
    workspace: CampaignLaneWorkspace,
    process_termination_timeout_seconds: float,
) -> Iterator[DistributedLaneSession]:
    if carrier not in CAMPAIGN_CARRIERS:
        raise ValueError(f"campaign carrier is invalid: {carrier}")
    execution_id = str((plan.get("executionIds") or {}).get(carrier) or "")
    if (
        plan.get("rootExecutionId") != root_execution_id
        or workspace.carrier != carrier
        or not execution_id
    ):
        raise ValueError("distributed campaign lane identity drift")
    run_id, generation, token = _distributed_identity(plan)
    path = lane_claim_path(runtime, root_execution_id, carrier)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f".{carrier}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                f"DATA.CAMPAIGN.LANE_ALREADY_CLAIMED carrier={carrier}"
            ) from exc
        previous = read_lane_claim(runtime, root_execution_id, carrier)
        if previous and str(previous.get("status") or "") in {
            "active",
            "starting",
            "running",
        }:
            terminate_lane_process(
                previous,
                grace_seconds=process_termination_timeout_seconds,
            )
        attempt = int((previous or {}).get("claimAttempt") or 0) + 1
        session = DistributedLaneSession(
            runtime=runtime,
            root_execution_id=root_execution_id,
            carrier=carrier,
            execution_id=execution_id,
            plan_digest=str(plan["planDigest"]),
            run_id=run_id,
            generation=generation,
            fencing_token=token,
            claim_id=_claim_identity(root_execution_id, carrier, attempt),
            claim_attempt=attempt,
            workspace=workspace,
            process_termination_timeout_seconds=process_termination_timeout_seconds,
            _mutex=threading.RLock(),
            _stop=threading.Event(),
        )
        session._write(status="active", phase="claim")
        session._heartbeat_thread = threading.Thread(
            target=session._heartbeat_loop,
            name=f"campaign-lane-heartbeat-{carrier}",
            daemon=True,
        )
        session._heartbeat_thread.start()
        try:
            with controller_signal_guard():
                yield session
        except BaseException as exc:
            try:
                session.abort_active_lanes()
            finally:
                session.finish(
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
            raise
        finally:
            session._stop.set()
            if session._heartbeat_thread is not None:
                session._heartbeat_thread.join(timeout=_HEARTBEAT_THREAD_JOIN_TIMEOUT_SECONDS)
            if not session._finished:
                session.finish(
                    status="interrupted",
                    error="DATA.CAMPAIGN.LANE_EXITED_WITHOUT_TERMINAL_STATE",
                )
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = [
    "DistributedLaneSession",
    "campaign_lane_claim_session",
    "lane_claim_path",
    "read_lane_claim",
]
