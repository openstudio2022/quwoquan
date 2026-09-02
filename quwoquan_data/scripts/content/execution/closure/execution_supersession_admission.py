"""Admission predicates deciding whether a frozen execution may be superseded.

Every predicate here reads only what is already on disk and refuses on doubt.
Writing the receipt lives in `content.execution.execution_supersession`; this
module never mutates the execution root.
"""

from __future__ import annotations

import hashlib
import json
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.schema import assert_valid

from content.execution.closure.execution_supersession_inventory import (
    _ANCHOR_REFS,
    _LIVENESS_PROBE,
    _optional_object,
    _optional_pid,
    _path_exists,
    _pgid_alive,
    _pid_alive,
    _require_regular_file,
)
from content.execution.stage_authority_validation import (
    validate_stage_receipt_authority,
)
from content.execution.stage_receipt import RECEIPT_STAGES, receipt_state_status
from content.execution.terminal_state_integrity import verify_terminal_state_integrity

_PRE_CONTROLLER_REQUIRED_FILES = frozenset(
    {
        "0.plan/execution_spec.yaml",
        "0.plan/queue_backend_envelope.json",
        "0.plan/request.json",
        "0.plan/target_set.json",
        "_shared/catalog.ndjson",
        "_shared/execution_progress.json",
        "_shared/target_selection.json",
        "evidence/model_readiness.json",
        "evidence/runtime_preflight.json",
        "execution_manifest.json",
        "sources/qualification/request.json",
    }
)
_PRE_CONTROLLER_OPTIONAL_FILES = frozenset({"_shared/execution_state.lock"})
_PRE_CONTROLLER_IDENTITY_FILES = frozenset(
    {
        "0.plan/queue_backend_envelope.json",
        "0.plan/target_set.json",
        "_shared/execution_progress.json",
        "_shared/target_selection.json",
        "evidence/model_readiness.json",
        "execution_manifest.json",
        "sources/qualification/request.json",
    }
)
_SUPERSESSION_ELIGIBLE_STATE_STATUSES = {"manual_required", "stopped_at_until"}
# 退役 managed 轨的 execution_state 是 AI 自报投影，不是 receipt-derived 事实。
# 这种冻结历史形状下连 `succeeded` 都不具备当前 receipt authority，且其 manifest
# 已不满足现行契约、永远不可 resume；supersession 是它唯一的合法终态出路。
_RETIRED_MANAGED_STATE_SCHEMA = "quwoquan.content.execution_state"
_RETIRED_MANAGED_ELIGIBLE_STATE_STATUSES = {
    "manual_required",
    "stopped_at_until",
    "succeeded",
}
# A `succeeded` execution is terminal-protected, and stays that way for every
# reason that argues about its inputs. It is reachable only for
# `unbound_completion_evidence`, where the claim is about the completion itself:
# the receipt chain says this execution shipped, while the evidence it cites
# belongs to a different release. Without this door such a receipt could never be
# retracted, and every later audit would keep counting it toward the delete
# admission. The door is narrow on purpose — the reason has to prove the
# mismatch from disk before it opens.
_COMPLETION_BOUND_ELIGIBLE_STATE_STATUSES = {"succeeded"}
_RELEASE_BUILD_FLAG = "--release-id"
_SHIP_RELEASE_FLAG = "--release"


def _settled_execution_state(root: Path) -> dict[str, Any] | None:
    state_path = root / _ANCHOR_REFS["executionState"]
    head_path = state_path.with_name("execution_state_head.json")
    events_path = state_path.with_name("execution_state_events")
    lock_path = state_path.with_name("execution_state.lock")
    state_exists = _path_exists(state_path)
    head_exists = _path_exists(head_path)
    events_exist = _path_exists(events_path)
    if _path_exists(lock_path):
        _require_regular_file(lock_path, label="execution state lock")
        if lock_path.stat().st_size != 0:
            raise ValueError("execution state lock must be empty")
    if not state_exists:
        if head_exists or events_exist:
            raise ValueError(
                "execution state is missing but journal fragments are present"
            )
        return None
    _require_regular_file(state_path, label="execution state snapshot")
    state = _optional_object(state_path)
    assert state is not None
    assert_valid(
        state,
        "execution",
        (
            "execution_state_retired_managed"
            if state.get("schema") == _RETIRED_MANAGED_STATE_SCHEMA
            else "execution_state"
        ),
        label=f"execution supersession state:{root.name}",
    )
    if state.get("executionId") != root.name:
        raise ValueError("execution supersession state executionId drift")
    if not head_exists:
        if events_exist:
            raise ValueError(
                "execution state journal has an uncommitted events directory"
            )
    else:
        _require_regular_file(head_path, label="execution state head")
        head = _optional_object(head_path)
        assert head is not None
        if head.get("executionId") != root.name:
            raise ValueError("execution state head executionId drift")
        try:
            sequence = int(head.get("sequence"))
        except (TypeError, ValueError) as exc:
            raise ValueError("execution state head sequence is invalid") from exc
        if events_path.is_symlink() or not events_path.is_dir():
            raise ValueError("execution state journal directory is missing or invalid")
        event_entries = sorted(events_path.iterdir(), key=lambda item: item.name)
        if any(item.is_symlink() or not item.is_file() for item in event_entries):
            raise ValueError("execution state journal contains a non-regular entry")
        expected_names = [f"{item:020d}.json" for item in range(1, sequence + 1)]
        if [item.name for item in event_entries] != expected_names:
            raise ValueError(
                "execution state journal is not settled at its committed head"
            )
    # Pure verifier: pending/torn journal recovery is forbidden above.
    verify_terminal_state_integrity(state_path)
    return state


def _validate_receipt_derived_state(
    root: Path,
    state: Mapping[str, Any],
) -> None:
    """Prove the current projection from the immutable stage receipt chain."""

    if state.get("schema") != "quwoquan.content.execution_state_projection":
        raise ValueError("workflow_drift requires current receipt-derived state")
    receipts_root = root / "_shared/receipts"
    if receipts_root.is_symlink() or not receipts_root.is_dir():
        raise ValueError("workflow_drift requires an immutable stage receipt chain")
    paths = sorted(receipts_root.iterdir(), key=lambda item: item.name)
    if not paths or len(paths) > len(RECEIPT_STAGES):
        raise ValueError("workflow_drift stage receipt chain is empty or oversized")
    completed: list[str] = []
    latest: dict[str, Any] | None = None
    latest_path: Path | None = None
    for index, receipt_path in enumerate(paths, start=1):
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise ValueError("workflow_drift stage receipt chain is not regular")
        expected_stage = RECEIPT_STAGES[index - 1]
        if receipt_path.name != f"{index:03d}-{expected_stage}.json":
            raise ValueError("workflow_drift stage receipt chain order drift")
        receipt = validate_stage_receipt_authority(
            root.name,
            receipt_path,
            verify_current_workflow=False,
        )
        if (
            receipt.get("executionId") != root.name
            or receipt.get("sequence") != index
            or receipt.get("stage") != expected_stage
        ):
            raise ValueError("workflow_drift stage receipt identity drift")
        if latest is not None and latest.get("verdict") != "pass":
            raise ValueError("workflow_drift blocked receipt has a successor")
        if receipt.get("verdict") == "pass":
            completed.append(expected_stage)
        latest = receipt
        latest_path = receipt_path
    assert latest is not None and latest_path is not None
    receipt_digest = "sha256:" + hashlib.sha256(latest_path.read_bytes()).hexdigest()
    expected = {
        "schema": "quwoquan.content.execution_state_projection",
        "executionId": root.name,
        "completed": completed,
        "status": receipt_state_status(latest).value,
        "latestStage": str(latest["stage"]),
        "next": str(latest["next"]),
        "latestReceiptRef": f"_shared/receipts/{latest_path.name}",
        "latestReceiptDigest": receipt_digest,
        "updatedAt": str(latest["recordedAt"]),
    }
    if dict(state) != expected:
        raise ValueError(
            "workflow_drift execution state is not the current receipt-derived projection"
        )


def _workflow_drift_state_status(
    root: Path,
    state: Mapping[str, Any] | None,
) -> str:
    if state is None:
        raise ValueError("workflow_drift supersession requires execution state")
    status = str(state.get("status") or "missing")
    eligible = set(_SUPERSESSION_ELIGIBLE_STATE_STATUSES)
    if state.get("schema") != _RETIRED_MANAGED_STATE_SCHEMA:
        eligible.add("running")
    if status not in eligible:
        raise ValueError(f"execution state is not supersession-eligible: {status}")
    if status == "running":
        _validate_receipt_derived_state(root, state)
    return status


def _validate_pre_controller_closure(
    root: Path,
    inventory: tuple[dict[str, object], ...],
) -> None:
    files = {
        str(entry["ref"])
        for entry in inventory
        if entry.get("kind") == "file"
    }
    missing = sorted(_PRE_CONTROLLER_REQUIRED_FILES - files)
    unexpected = sorted(
        files - _PRE_CONTROLLER_REQUIRED_FILES - _PRE_CONTROLLER_OPTIONAL_FILES
    )
    if missing or unexpected:
        raise ValueError(
            "missing-state execution is not an exact pre-controller closure: "
            f"missing={missing} unexpected={unexpected}"
        )
    for relative in sorted(_PRE_CONTROLLER_REQUIRED_FILES):
        path = root / relative
        if relative.endswith(".json"):
            _optional_object(path)
        elif relative.endswith(".ndjson"):
            lines = path.read_text(encoding="utf-8").splitlines()
            if not lines:
                raise ValueError("pre-controller catalog must not be empty")
            for line in lines:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("pre-controller catalog rows must be objects")
        elif path.stat().st_size == 0:
            raise ValueError(f"pre-controller evidence must not be empty: {relative}")
    for relative in _PRE_CONTROLLER_IDENTITY_FILES:
        document = _optional_object(root / relative)
        if document is None or document.get("executionId") != root.name:
            raise ValueError(
                f"pre-controller evidence executionId drift: {relative}"
            )
    progress = _optional_object(root / "_shared/execution_progress.json") or {}
    counts = progress.get("counts")
    if progress.get("lastRunId") is not None or not isinstance(counts, Mapping):
        raise ValueError("pre-controller progress contains runtime evidence")
    if any(int(counts.get(name) or 0) != 0 for name in ("entities", "posts")):
        raise ValueError("pre-controller progress contains finalized objects")


def _release_identity_from_command(command: str, flag: str) -> str | None:
    """Read the release identity a recorded command actually operated on."""
    tokens = command.split()
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith(f"{flag}="):
            return token.split("=", 1)[1]
    return None


def _stage_release_identity(
    receipts_root: Path, *, stage: str, flag: str
) -> tuple[str | None, str | None]:
    """Find the release identity the last passing receipt for `stage` names.

    Only a passing receipt counts. A blocked attempt at the same stage records
    what was tried, not what the execution stands on, so letting it answer would
    let a failed ship supply the identity a later passing one contradicts.
    """
    if not receipts_root.is_dir():
        return None, None
    for path in sorted(receipts_root.glob(f"*-{stage}.json"), reverse=True):
        document = _optional_object(path)
        if not isinstance(document, Mapping):
            continue
        if document.get("verdict") != "pass":
            continue
        authority = document.get("authority")
        if isinstance(authority, Mapping):
            release_binding = authority.get("releaseBinding")
            if isinstance(release_binding, Mapping):
                identity = str(release_binding.get("releaseId") or "")
                return (identity or None), path.name
            return None, path.name
        # 冻结历史 receipt 只读兼容：旧 schema 只能从已记录命令提取 identity。
        commands = (document.get("evidence") or {}).get("commands") or []
        for entry in commands:
            if not isinstance(entry, Mapping):
                continue
            identity = _release_identity_from_command(
                str(entry.get("command") or ""), flag
            )
            if identity:
                return identity, path.name
        return None, path.name
    return None, None


def _completion_evidence_binding(root: Path) -> dict[str, object]:
    """Prove, from this execution's own receipts, that its completion is unbound.

    The predicate is deliberately narrow and fully on-disk: the release stage
    records which release this execution built, the ship stage records which
    release it shipped and verified. When those two disagree, the ship evidence
    describes someone else's release, and the `succeeded` verdict rests on it.
    Agreement — or a missing half — refuses, so the reason cannot be used to walk
    back an execution whose completion is its own.
    """
    receipts_root = root / "_shared/receipts"
    built, built_ref = _stage_release_identity(
        receipts_root, stage="release", flag=_RELEASE_BUILD_FLAG
    )
    shipped, shipped_ref = _stage_release_identity(
        receipts_root, stage="ship", flag=_SHIP_RELEASE_FLAG
    )
    if built is None or shipped is None:
        raise ValueError(
            "unbound_completion_evidence supersession requires both a passing "
            "release receipt naming the release this execution built and a passing "
            "ship receipt naming the release it shipped; "
            f"built={built!r} shipped={shipped!r}"
        )
    if built == shipped:
        raise ValueError(
            "unbound_completion_evidence supersession requires the shipped release "
            f"to differ from the built one; both are {built!r}"
        )
    return {
        "builtReleaseId": built,
        "builtReleaseReceiptRef": built_ref,
        "shippedReleaseId": shipped,
        "shippedReleaseReceiptRef": shipped_ref,
    }


def _lease_disposition(lease: Mapping[str, Any] | None) -> str:
    """Name how the controller lease ended, without letting it claim liveness.

    一个被 SIGKILL 的控制器留下的 `active` 记录只是写它的那个进程留下的意图，能否判它
    已弃置由调用方紧接着做的 pid/pgid 观测裁定。反过来，一条既写 `active` 又不记
    pid/pgid 的租约没有任何可观测基础，此时缺席不是「已死」，仍然判否——否则
    `manual_required` 加已死控制器的 execution 就再没有任何终态出路，而无记录的租约
    又会被当成已死。
    """
    if lease is None:
        return "absent"
    status = str(lease.get("status") or "").strip()
    if status == "released":
        return "released"
    if status != "active":
        raise ValueError("execution controller lease status is invalid")
    if _optional_pid(lease.get("pid")) is None and _optional_pid(lease.get("pgid")) is None:
        raise ValueError(
            "execution controller lease is active with no recorded process identity; "
            "supersession refused"
        )
    return "abandoned_dead_process"


def _process_evidence(
    root: Path,
    *,
    execution_id: str,
    state: Mapping[str, Any] | None,
    reason: str,
) -> tuple[dict[str, object], str, str]:
    lease = _optional_object(root / _ANCHOR_REFS["controllerLease"])
    if lease is not None and lease.get("executionId") != execution_id:
        raise ValueError("execution controller lease executionId drift")
    lease_disposition = _lease_disposition(lease)
    state_status = str((state or {}).get("status") or "missing")
    if reason == "workflow_drift":
        # workflow_drift 只为 current receipt-derived running 打开窄门；不得继承
        # retired managed 对 succeeded 的历史豁免。
        state_status = _workflow_drift_state_status(root, state)
    else:
        eligible = set(_SUPERSESSION_ELIGIBLE_STATE_STATUSES)
        if state is not None and state.get("schema") == _RETIRED_MANAGED_STATE_SCHEMA:
            eligible = set(_RETIRED_MANAGED_ELIGIBLE_STATE_STATUSES)
        if reason == "unbound_completion_evidence":
            eligible = set(_COMPLETION_BOUND_ELIGIBLE_STATE_STATUSES)
        if state is not None and state_status not in eligible:
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
        lease_disposition,
    )
