"""Filesystem inventory for execution supersession."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.execution.execution_supersession import (
    Path,
    _digest,
    _file_digest,
    stat,
)


def _root_inventory(root: Path) -> tuple[tuple[dict[str, object], ...], str]:
    entries: list[dict[str, object]] = []
    candidates = sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    )
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        parts = Path(relative).parts
        if parts[:2] == ("_shared", "reconciliation"):
            if len(parts) == 2 and (path.is_symlink() or not path.is_dir()):
                raise ValueError(
                    "execution supersession reconciliation root is corrupt"
                )
            continue
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(
                f"execution supersession root contains a symlink: {relative}"
            )
        if stat.S_ISDIR(metadata.st_mode):
            entries.append(
                {"ref": relative, "kind": "directory", "size": None, "sha256": None}
            )
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(
                f"execution supersession root contains a non-regular entry: {relative}"
            )
        entries.append(
            {
                "ref": relative,
                "kind": "file",
                "size": metadata.st_size,
                "sha256": _file_digest(path),
            }
        )
    frozen = tuple(entries)
    return frozen, _digest({"entries": list(frozen)})


def _process_evidence(
    root: Path,
    *,
    execution_id: str,
    state: Mapping[str, Any] | None,
) -> tuple[dict[str, object], str]:
    from content.execution.execution_supersession import (
        _ANCHOR_REFS,
        _LIVENESS_PROBE,
        _SUPERSESSION_ELIGIBLE_STATE_STATUSES,
        _optional_object,
        _optional_pid,
        _pgid_alive,
        _pid_alive,
        socket,
    )

    lease = _optional_object(root / _ANCHOR_REFS["controllerLease"])
    if lease is not None:
        if lease.get("executionId") != execution_id:
            raise ValueError("execution controller lease executionId drift")
        lease_status = str(lease.get("status") or "").strip()
        if lease_status == "active":
            raise ValueError(
                "execution controller lease is active; supersession refused"
            )
        if lease_status != "released":
            raise ValueError("execution controller lease status is invalid")
    state_status = str((state or {}).get("status") or "missing")
    if state is not None and state_status not in _SUPERSESSION_ELIGIBLE_STATE_STATUSES:
        raise ValueError(
            f"execution state is not supersession-eligible: {state_status}"
        )
    controller = state.get("controller") if state else None
    controller_row = controller if isinstance(controller, Mapping) else {}
    pid = _optional_pid((lease or {}).get("pid") or controller_row.get("pid"))
    pgid = _optional_pid((lease or {}).get("pgid") or controller_row.get("pgid"))
    observed_pid_alive = _pid_alive(pid)
    observed_group_alive = _pgid_alive(pgid)
    if observed_pid_alive or observed_group_alive:
        raise ValueError(
            "execution controller/process group is still alive; supersession refused"
        )
    return (
        {
            "hostname": socket.gethostname(),
            "pid": pid,
            "pgid": pgid,
            "observedPidAlive": observed_pid_alive,
            "observedProcessGroupAlive": observed_group_alive,
            "identityMatched": False,
            "pidAlive": False,
            "processGroupAlive": False,
            "livenessProbe": _LIVENESS_PROBE,
        },
        state_status,
    )
