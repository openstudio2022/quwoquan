"""Resolve and probe the Ops-owned ReliableTask fleet transport."""
from __future__ import annotations

from contextlib import contextmanager
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse

from core.paths import DATA_LOCAL_ROOT, REPO_ROOT


_STACKCTL_PATH = REPO_ROOT / "quwoquan_ops" / "cli" / "stackctl.py"


@dataclass(frozen=True, slots=True)
class ReliableTaskFleetTransport:
    target: str
    mongo_uri: str
    redis_addr: str

    @classmethod
    def from_document(cls, value: object) -> "ReliableTaskFleetTransport":
        if not isinstance(value, Mapping):
            raise ValueError("ReliableTask fleet transport must be an object")
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
        raise RuntimeError("ReliableTask fleet topology result must be an object")
    exit_code = document.get("exitCode")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code != 0:
        raise RuntimeError("ReliableTask fleet topology reported failure")
    return document


def resolve_reliabletask_fleet_transport() -> ReliableTaskFleetTransport:
    """Resolve runtime endpoints only through the Ops-owned topology facade."""
    document = _stackctl_fleet_document()
    return ReliableTaskFleetTransport.from_document(document.get("fleet"))


def _ensure_reliabletask_fleet_transport(
    expected: ReliableTaskFleetTransport,
) -> None:
    """Reconcile a missing dedicated fleet only through stackctl."""
    document = _stackctl_fleet_document("--action", "up")
    actual = ReliableTaskFleetTransport.from_document(document.get("fleet"))
    evidence = document.get("evidence")
    if actual != expected or not isinstance(evidence, Mapping) or evidence.get("ready") is not True:
        raise RuntimeError("ReliableTask fleet reconcile did not restore frozen transport")


def _transport_socket_parts(
    transport: ReliableTaskFleetTransport,
) -> tuple[tuple[str, int], tuple[str, int]]:
    mongo = urlparse(transport.mongo_uri)
    redis_host, _, redis_port = transport.redis_addr.rpartition(":")
    if mongo.hostname is None or mongo.port is None:
        raise ValueError("ReliableTask fleet Mongo endpoint is invalid")
    return (mongo.hostname, mongo.port), (redis_host, int(redis_port))


@contextmanager
def _fleet_reconciliation_guard():
    """Serialize readiness checks with side-effecting stackctl reconciliation."""
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
    """Probe the resolved fleet control plane before expensive source work starts."""
    with _fleet_reconciliation_guard():
        transport = resolve_reliabletask_fleet_transport()
        from core.runtime_policy import active_runtime_policy

        timeout = float(active_runtime_policy().preflight_network_timeout_seconds)
        if not _fleet_transport_ready(transport, socket_timeout_seconds=timeout):
            _ensure_reliabletask_fleet_transport(transport)
        mongo, redis = _transport_socket_parts(transport)
        checks: list[tuple[str, tuple[str, int]]] = [("mongo", mongo), ("redis", redis)]
        outcomes: dict[str, bool] = {}
        issues: list[str] = []
        for name, address in checks:
            try:
                with socket.create_connection(address, timeout=timeout):
                    outcomes[name] = True
            except OSError as exc:
                outcomes[name] = False
                issues.append(f"{name} endpoint unavailable: {type(exc).__name__}")
        return {
            "ready": not issues,
            "target": transport.target,
            "mongo": outcomes["mongo"],
            "redis": outcomes["redis"],
            "issues": issues,
        }


def _fleet_transport_ready(
    transport: ReliableTaskFleetTransport,
    *,
    socket_timeout_seconds: float,
) -> bool:
    for address in _transport_socket_parts(transport):
        try:
            with socket.create_connection(address, timeout=socket_timeout_seconds):
                pass
        except OSError:
            return False
    return True


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
    reconciled = False
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
            if not reconciled:
                try:
                    _ensure_reliabletask_fleet_transport(transport)
                except RuntimeError:
                    # Docker may itself still be restarting.  Preserve the
                    # bounded socket wait and keep probing the frozen endpoint.
                    pass
                reconciled = True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(retry_delay_seconds, remaining))
