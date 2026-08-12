"""Resolve and probe the Ops-owned ReliableTask fleet transport."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlparse

from core.paths import DATA_LOCAL_ROOT, REPO_ROOT

_STACKCTL_PATH = REPO_ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
FLEET_TARGET_ENV = "QWQ_RELIABLETASK_FLEET_TARGET"
FLEET_MONGO_URI_ENV = "QWQ_RELIABLETASK_FLEET_MONGO_URI"
FLEET_REDIS_ADDR_ENV = "QWQ_RELIABLETASK_FLEET_REDIS_ADDR"
FLEET_PLAN_DIGEST_ENV = "QWQ_RELIABLETASK_FLEET_PLAN_DIGEST"
FLEET_BINDING_DIGEST_ENV = "QWQ_RELIABLETASK_FLEET_BINDING_DIGEST"
CAMPAIGN_ROOT_ENV = "QWQ_CAMPAIGN_ROOT_EXECUTION_ID"
_FLEET_ENV_NAMES = (
    FLEET_TARGET_ENV,
    FLEET_MONGO_URI_ENV,
    FLEET_REDIS_ADDR_ENV,
    FLEET_PLAN_DIGEST_ENV,
    FLEET_BINDING_DIGEST_ENV,
)


@dataclass(frozen=True, slots=True)
class ReliableTaskFleetTransport:
    target: str
    mongo_uri: str
    redis_addr: str

    @classmethod
    def from_document(cls, value: object) -> ReliableTaskFleetTransport:
        if not isinstance(value, Mapping):
            raise TypeError("ReliableTask fleet transport must be an object")
        expected_fields = {"target", "mongoUri", "redisAddr"}
        if set(value) != expected_fields:
            raise ValueError("ReliableTask fleet transport fields are invalid")
        target = str(value.get("target") or "").strip()
        mongo_uri = str(value.get("mongoUri") or "").strip()
        redis_addr = str(value.get("redisAddr") or "").strip()
        parsed = urlparse(mongo_uri)
        host, separator, port = redis_addr.rpartition(":")
        if (
            not target
            or parsed.scheme != "mongodb"
            or not parsed.hostname
            or parsed.port is None
            or not host
            or not separator
            or not port.isdecimal()
        ):
            raise ValueError("ReliableTask fleet transport values are invalid")
        return cls(target=target, mongo_uri=mongo_uri, redis_addr=redis_addr)


@dataclass(frozen=True, slots=True)
class FrozenReliableTaskFleetBinding:
    root_execution_id: str
    plan_digest: str
    transport: ReliableTaskFleetTransport
    binding_digest: str

    @classmethod
    def create(
        cls,
        *,
        root_execution_id: str,
        plan_digest: str,
        transport: ReliableTaskFleetTransport,
    ) -> FrozenReliableTaskFleetBinding:
        stable = {
            "rootExecutionId": root_execution_id,
            "planDigest": plan_digest,
            **transport_document(transport),
        }
        return cls(
            root_execution_id=root_execution_id,
            plan_digest=plan_digest,
            transport=transport,
            binding_digest=_binding_digest(stable),
        )

    @classmethod
    def from_document(cls, value: object) -> FrozenReliableTaskFleetBinding:
        if not isinstance(value, Mapping):
            raise TypeError("ReliableTask frozen fleet binding must be an object")
        expected = {
            "rootExecutionId",
            "planDigest",
            "target",
            "mongoUri",
            "redisAddr",
            "bindingDigest",
        }
        if set(value) != expected:
            raise ValueError("ReliableTask frozen fleet binding fields are invalid")
        root_execution_id = str(value.get("rootExecutionId") or "").strip()
        plan_digest = str(value.get("planDigest") or "").strip()
        binding_digest = str(value.get("bindingDigest") or "").strip()
        if not root_execution_id or not _is_sha256(plan_digest):
            raise ValueError("ReliableTask frozen fleet campaign identity is invalid")
        transport = ReliableTaskFleetTransport.from_document(
            {
                "target": value.get("target"),
                "mongoUri": value.get("mongoUri"),
                "redisAddr": value.get("redisAddr"),
            }
        )
        binding = cls.create(
            root_execution_id=root_execution_id,
            plan_digest=plan_digest,
            transport=transport,
        )
        if binding_digest != binding.binding_digest:
            raise ValueError("ReliableTask frozen fleet binding digest drift")
        return binding

    def document(self) -> dict[str, str]:
        return {
            "rootExecutionId": self.root_execution_id,
            "planDigest": self.plan_digest,
            **transport_document(self.transport),
            "bindingDigest": self.binding_digest,
        }

    def environment(self) -> dict[str, str]:
        return {
            FLEET_TARGET_ENV: self.transport.target,
            FLEET_MONGO_URI_ENV: self.transport.mongo_uri,
            FLEET_REDIS_ADDR_ENV: self.transport.redis_addr,
            FLEET_PLAN_DIGEST_ENV: self.plan_digest,
            FLEET_BINDING_DIGEST_ENV: self.binding_digest,
        }


def _is_sha256(value: str) -> bool:
    return len(value) == 71 and value.startswith("sha256:") and all(
        char in "0123456789abcdef" for char in value[7:]
    )


def _binding_digest(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def transport_document(transport: ReliableTaskFleetTransport) -> dict[str, str]:
    return {
        "target": transport.target,
        "mongoUri": transport.mongo_uri,
        "redisAddr": transport.redis_addr,
    }


def _campaign_fleet_binding_from_environment() -> FrozenReliableTaskFleetBinding:
    root_execution_id = str(os.environ.get(CAMPAIGN_ROOT_ENV) or "").strip()
    values = {name: str(os.environ.get(name) or "").strip() for name in _FLEET_ENV_NAMES}
    if not root_execution_id or any(not value for value in values.values()):
        raise RuntimeError("campaign ReliableTask fleet binding is incomplete")
    return FrozenReliableTaskFleetBinding.from_document(
        {
            "rootExecutionId": root_execution_id,
            "planDigest": values[FLEET_PLAN_DIGEST_ENV],
            "target": values[FLEET_TARGET_ENV],
            "mongoUri": values[FLEET_MONGO_URI_ENV],
            "redisAddr": values[FLEET_REDIS_ADDR_ENV],
            "bindingDigest": values[FLEET_BINDING_DIGEST_ENV],
        }
    )


def _stackctl_fleet_document(*arguments: str) -> Mapping[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(_STACKCTL_PATH),
            "--output-format",
            "json",
            "data-execution-fleet",
            *arguments,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or "no diagnostic output"
        raise RuntimeError(f"ReliableTask fleet topology is unavailable: {detail}")
    try:
        document = json.loads(completed.stdout)
    except ValueError as exc:
        raise RuntimeError("ReliableTask fleet topology returned invalid JSON") from exc
    if not isinstance(document, Mapping):
        raise TypeError("ReliableTask fleet topology result must be an object")
    exit_code = document.get("exitCode")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code != 0:
        raise RuntimeError("ReliableTask fleet topology reported failure")
    return document


def _resolve_stackctl_fleet_transport() -> ReliableTaskFleetTransport:
    """Resolve runtime endpoints only through the Ops-owned topology facade."""
    document = _stackctl_fleet_document()
    return ReliableTaskFleetTransport.from_document(document.get("fleet"))


def resolve_reliabletask_fleet_transport() -> ReliableTaskFleetTransport:
    """Resolve controller topology or consume one plan-bound campaign binding."""
    if str(os.environ.get(CAMPAIGN_ROOT_ENV) or "").strip():
        return _campaign_fleet_binding_from_environment().transport
    return _resolve_stackctl_fleet_transport()


@contextmanager
def _fleet_status_guard():
    """Serialize protocol-level status probes without mutating the fleet."""
    lock_path = DATA_LOCAL_ROOT / "cache" / "reliabletask-fleet-preflight.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl  # type: ignore
    except Exception:  # noqa: BLE001
        yield
        return
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def reliabletask_fleet_preflight() -> dict[str, object]:
    """Read the Ops-owned, protocol-level fleet status without reconciling it."""
    with _fleet_status_guard():
        if str(os.environ.get(CAMPAIGN_ROOT_ENV) or "").strip():
            binding = _campaign_fleet_binding_from_environment()
            document = _stackctl_fleet_document("--action", "status")
            actual = ReliableTaskFleetTransport.from_document(document.get("fleet"))
            evidence = document.get("evidence")
            if not isinstance(evidence, Mapping):
                raise RuntimeError("ReliableTask fleet status omitted typed evidence")
            mongo_ready = evidence.get("mongo") is True
            redis_ready = evidence.get("redis") is True
            owned = evidence.get("owned") is True
            ready = bool(
                actual == binding.transport
                and evidence.get("ready") is True
                and mongo_ready
                and redis_ready
                and owned
            )
            return {
                "checked": True,
                "ready": ready,
                "target": binding.transport.target,
                "mongo": mongo_ready,
                "redis": redis_ready,
                "owned": owned,
                "issues": (
                    []
                    if ready
                    else ["dedicated ReliableTask fleet is not writable"]
                ),
            }
        document = _stackctl_fleet_document("--action", "status")
        transport = ReliableTaskFleetTransport.from_document(document.get("fleet"))
        evidence = document.get("evidence")
        if not isinstance(evidence, Mapping):
            raise RuntimeError("ReliableTask fleet status omitted typed evidence")
        mongo_ready = evidence.get("mongo") is True
        redis_ready = evidence.get("redis") is True
        owned = evidence.get("owned") is True
        ready = evidence.get("ready") is True and mongo_ready and redis_ready and owned
        issues = [] if ready else ["dedicated ReliableTask fleet is not writable"]
        return {
            "ready": ready,
            "target": transport.target,
            "mongo": mongo_ready,
            "redis": redis_ready,
            "owned": owned,
            "issues": issues,
        }


def require_pool_delivery_fleet_transport() -> ReliableTaskFleetTransport:
    """Resolve the Data-owned fleet without trusting transient lane environment.

    Pool delivery may be drained after the semantic campaign process exited, so
    its topology proof must come from the Ops status document itself.  This is
    deliberately read-only and never reconciles or starts the fleet.
    """

    document = _stackctl_fleet_document("--action", "status")
    transport = ReliableTaskFleetTransport.from_document(document.get("fleet"))
    evidence = document.get("evidence")
    if not (
        transport.target == "data-local"
        and isinstance(evidence, Mapping)
        and evidence.get("ready") is True
        and evidence.get("mongo") is True
        and evidence.get("redis") is True
        and evidence.get("owned") is True
    ):
        raise RuntimeError("Data pool delivery fleet is not writable")
    return transport


def pool_delivery_fleet_preflight(
    expected: ReliableTaskFleetTransport,
) -> dict[str, object]:
    """Read back the exact transport frozen for one pool-delivery epoch."""

    with _fleet_status_guard():
        document = _stackctl_fleet_document("--action", "status")
        actual = ReliableTaskFleetTransport.from_document(document.get("fleet"))
        evidence = document.get("evidence")
        if not isinstance(evidence, Mapping):
            raise RuntimeError("ReliableTask fleet status omitted typed evidence")
        mongo_ready = evidence.get("mongo") is True
        redis_ready = evidence.get("redis") is True
        owned = evidence.get("owned") is True
        ready = bool(
            actual == expected
            and expected.target == "data-local"
            and evidence.get("ready") is True
            and mongo_ready
            and redis_ready
            and owned
        )
        return {
            "ready": ready,
            "target": expected.target,
            "mongo": mongo_ready,
            "redis": redis_ready,
            "owned": owned,
            "issues": [] if ready else ["dedicated Data pool delivery fleet is not writable"],
        }


def prepare_controller_reliabletask_fleet_transport() -> ReliableTaskFleetTransport:
    """Require an explicitly started fleet before freezing it into campaign lanes."""
    if str(os.environ.get(CAMPAIGN_ROOT_ENV) or "").strip() or any(
        str(os.environ.get(name) or "").strip() for name in _FLEET_ENV_NAMES
    ):
        raise RuntimeError("campaign controller cannot inherit a lane fleet binding")
    document = _stackctl_fleet_document("--action", "status")
    transport = ReliableTaskFleetTransport.from_document(document.get("fleet"))
    evidence = document.get("evidence")
    if not (
        isinstance(evidence, Mapping)
        and evidence.get("ready") is True
        and evidence.get("mongo") is True
        and evidence.get("redis") is True
        and evidence.get("owned") is True
    ):
        raise RuntimeError(
            "ReliableTask fleet is unavailable; run the explicit stackctl "
            "data-execution-fleet up operation first"
        )
    return transport


def _fleet_transport_ready(
    transport: ReliableTaskFleetTransport,
    *,
    socket_timeout_seconds: float,
) -> bool:
    del socket_timeout_seconds
    try:
        document = _stackctl_fleet_document("--action", "status")
        actual = ReliableTaskFleetTransport.from_document(document.get("fleet"))
    except (RuntimeError, TypeError, ValueError):
        return False
    evidence = document.get("evidence")
    return bool(
        actual == transport
        and isinstance(evidence, Mapping)
        and evidence.get("ready") is True
        and evidence.get("mongo") is True
        and evidence.get("redis") is True
        and evidence.get("owned") is True
    )


def _wait_for_fleet_transport(
    transport: ReliableTaskFleetTransport,
    *,
    timeout_seconds: float,
    retry_delay_seconds: float,
    socket_timeout_seconds: float,
    required_ready_probes: int = 1,
) -> bool:
    """Wait for a bounded backend recovery window before restarting a worker."""
    if required_ready_probes < 1:
        raise ValueError("ReliableTask fleet ready probe count must be positive")
    ready_streak = 0
    deadline = time.monotonic() + timeout_seconds
    while True:
        if _fleet_transport_ready(
            transport,
            socket_timeout_seconds=socket_timeout_seconds,
        ):
            ready_streak += 1
            if ready_streak >= required_ready_probes:
                return True
        else:
            ready_streak = 0
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(retry_delay_seconds, remaining))
