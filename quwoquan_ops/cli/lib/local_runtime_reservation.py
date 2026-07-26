from __future__ import annotations

import fcntl
import os
import socket
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from quwoquan_ops.cli.lib.common import utc_now
from quwoquan_ops.cli.lib.output_paths import repo_local_dir


PortProbe = Callable[[str, int], bool]


def local_runtime_operation_lock_path() -> Path:
    return repo_local_dir("local-runtime") / ".stackctl-operation.lock"


def acquire_local_runtime_use_lock(
    *,
    target: str,
    purpose: str,
    lock_path: Path | None = None,
) -> Any:
    """持有本地运行时共享租约，阻止 UAT 期间被 stackctl 启停。"""
    path = lock_path or local_runtime_operation_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.seek(0)
        holder = handle.read().strip() or "unknown"
        handle.close()
        raise RuntimeError(
            f"local runtime operation is already running: {holder}"
        ) from error
    handle.seek(0)
    handle.truncate()
    handle.write(
        f"pid={os.getpid()} target={target.strip()} purpose={purpose.strip()} "
        f"startedAt={utc_now()}\n"
    )
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def _tcp_port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def active_conflicting_local_targets(
    topology: Mapping[str, Any],
    requested_target: str,
    *,
    port_probe: PortProbe = _tcp_port_is_open,
) -> tuple[str, ...]:
    """返回与目标争用同一主机资源组、且已在运行的其他本地环境。"""
    targets = topology.get("targets")
    if not isinstance(targets, Mapping):
        raise RuntimeError("environment topology targets must be a mapping")
    requested = targets.get(requested_target)
    if not isinstance(requested, Mapping):
        raise RuntimeError(f"unknown local runtime target: {requested_target}")
    resource_group = str(requested.get("localResourceGroup") or "").strip()
    if not resource_group:
        return ()

    active: list[str] = []
    for candidate_name, candidate in targets.items():
        if candidate_name == requested_target or not isinstance(candidate, Mapping):
            continue
        if str(candidate.get("backend") or "").strip() != "local":
            continue
        if str(candidate.get("localResourceGroup") or "").strip() != resource_group:
            continue
        origins = candidate.get("origins")
        if not isinstance(origins, Mapping):
            continue
        content_origin = str(origins.get("contentService") or "").strip()
        parsed = urlparse(content_origin)
        if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port is None:
            continue
        if port_probe(parsed.hostname, parsed.port):
            active.append(str(candidate_name))
    return tuple(sorted(active))


def assert_local_runtime_available(
    topology: Mapping[str, Any],
    requested_target: str,
    *,
    port_probe: PortProbe = _tcp_port_is_open,
) -> None:
    conflicts = active_conflicting_local_targets(
        topology,
        requested_target,
        port_probe=port_probe,
    )
    if not conflicts:
        return
    shutdowns = ", ".join(
        f"`python3 quwoquan_ops/cli/stackctl.py down --target {target}`"
        for target in conflicts
    )
    raise RuntimeError(
        f"{requested_target} cannot start while local runtime "
        f"{', '.join(conflicts)} is active; stop it with {shutdowns}"
    )
