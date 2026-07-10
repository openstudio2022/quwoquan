"""Operational governance contracts for company-style data production.

This module is intentionally small and file-backed.  It gives the workflow a
single batch controller, explicit assignment ownership, source-unit atomicity
checks, and auditable failure/conflict ledgers without introducing a second
runtime service.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from _common.io import read_json, write_json
from _common.paths import batch_root
from task import store

CONTROLLER_LEASE_SCHEMA = "quwoquan_data.controller_lease/1"
RUNTIME_PROTECTION_SCHEMA = "quwoquan_data.runtime_protection/1"
ASSIGNMENT_SCHEMA = "quwoquan_data.assignment/1"
ASSIGNMENT_STATE_SCHEMA = "quwoquan_data.assignment_state/1"
ASSIGNMENT_EVENT_SCHEMA = "quwoquan_data.assignment_event/1"
CONFLICT_LEDGER_SCHEMA = "quwoquan_data.conflict_ledger/1"
FAILURE_LEDGER_SCHEMA = "quwoquan_data.failure_ledger/1"
QUALITY_TARGET_REPORT_SCHEMA = "quwoquan_data.quality_target_report/1"

DEFAULT_CONTROLLER_STALE_SECONDS = 15 * 60
DEFAULT_ASSIGNMENT_DEADLINE_SECONDS = 20 * 60

FAILURE_INFRA_RETRY = "retry.infra"
FAILURE_DATA_RETRY = "retry.data"
FAILURE_QUALITY_REPAIR = "repair.quality"
FAILURE_ABANDON = "abandon"
FAILURE_CONFLICT = "conflict"
FAILURE_GATE_BLOCK = "blocked.gate"
FAILURE_MANUAL_REVIEW = "manual_review"

FINAL_FAILURE_CATEGORIES = {
    FAILURE_INFRA_RETRY,
    FAILURE_DATA_RETRY,
    FAILURE_QUALITY_REPAIR,
    FAILURE_ABANDON,
    FAILURE_CONFLICT,
    FAILURE_GATE_BLOCK,
    FAILURE_MANUAL_REVIEW,
}


def _shared_dir(task_id: str, batch_id: str, *, create: bool = True) -> Path:
    path = batch_root(task_id, batch_id) / "_shared"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def controller_lease_path(task_id: str, batch_id: str, *, create: bool = False) -> Path:
    return _shared_dir(task_id, batch_id, create=create) / "controller_lease.json"


def controller_lease_lock_path(task_id: str, batch_id: str) -> Path:
    return _shared_dir(task_id, batch_id) / "controller_lease.lock"


def assignment_ledger_path(task_id: str, batch_id: str) -> Path:
    return _shared_dir(task_id, batch_id) / "assignment_ledger.jsonl"


def assignment_state_path(task_id: str, batch_id: str) -> Path:
    return _shared_dir(task_id, batch_id) / "assignment_state.json"


def assignment_events_path(task_id: str, batch_id: str) -> Path:
    return _shared_dir(task_id, batch_id) / "assignment_events.jsonl"


def conflict_ledger_path(task_id: str, batch_id: str) -> Path:
    return _shared_dir(task_id, batch_id) / "conflict_ledger.jsonl"


def failure_ledger_path(task_id: str, batch_id: str) -> Path:
    return _shared_dir(task_id, batch_id) / "failure_ledger.jsonl"


def quality_target_report_path(task_id: str, batch_id: str) -> Path:
    return _shared_dir(task_id, batch_id) / "quality_target_report.json"


def runtime_protection_manifest_path(task_id: str, batch_id: str, *, create: bool = False) -> Path:
    return _shared_dir(task_id, batch_id, create=create) / "runtime_protection.json"


def write_runtime_protection_manifest(
    task_id: str,
    batch_id: str,
    *,
    plan_id: str | None = None,
    protected_paths: Sequence[str] = (),
    note: str = "",
) -> Path:
    """跑批保护协议：声明本批次活跃期间禁止外部治理代理清理/终止的资源清单。

    WP5 实测外部治理代理会拒杀长跑进程并清理 runtime 产物。协议约定：
    - 任何外部清理动作前必须读取本清单；`pid` 存活且 lease 活跃时，清单内
      路径（frozen plan、release 产物、workflow state、object queue）不得
      删除/覆盖，进程树不得 kill；
    - 清单与 controller lease 同目录同源（`_shared/`），批次收口后随批次
      证据留档，不需要显式解除。
    """
    from _common.paths import OUTPUT_ROOT, fanout_plan_path

    defaults: list[str] = [
        str(batch_root(task_id, batch_id)),
        str(controller_lease_path(task_id, batch_id)),
    ]
    if plan_id:
        try:
            defaults.append(str(fanout_plan_path(plan_id)))
        except Exception:  # noqa: BLE001
            pass
    release_root = OUTPUT_ROOT / "release"
    if release_root.is_dir():
        defaults.append(str(release_root))
    merged = list(dict.fromkeys([*defaults, *[str(p) for p in protected_paths if str(p)]]))
    manifest = {
        "schema": RUNTIME_PROTECTION_SCHEMA,
        "taskId": task_id,
        "batchId": batch_id,
        "planId": plan_id or None,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "startedAt": store.now_iso(),
        "protectedPaths": merged,
        "leaseRef": str(controller_lease_path(task_id, batch_id)),
        "note": note or (
            "active batch runtime protection: do not kill process tree or delete "
            "protected paths while pid is alive"
        ),
    }
    path = runtime_protection_manifest_path(task_id, batch_id, create=True)
    write_json(path, manifest)
    return path


def _now_epoch() -> float:
    return time.time()


def _parse_iso_seconds(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def pid_alive(pid: object) -> bool:
    try:
        value = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def new_controller_run_id(task_id: str, batch_id: str, *, pid: int | None = None) -> str:
    seed = f"{task_id}|{batch_id}|{pid or os.getpid()}|{socket.gethostname()}|{store.now_iso()}|{time.monotonic_ns()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def read_controller_lease(task_id: str, batch_id: str) -> dict[str, Any] | None:
    path = controller_lease_path(task_id, batch_id, create=False)
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def controller_lease_active(
    lease: Mapping[str, Any] | None,
    *,
    current_pid: int | None = None,
    stale_seconds: int = DEFAULT_CONTROLLER_STALE_SECONDS,
) -> bool:
    if not isinstance(lease, Mapping):
        return False
    if str(lease.get("status") or "active") != "active":
        return False
    pid = int(lease.get("pid") or 0)
    if current_pid is not None and pid == current_pid:
        return False
    if pid_alive(pid):
        return True
    heartbeat = _parse_iso_seconds(lease.get("heartbeatAt") or lease.get("startedAt"))
    return heartbeat is not None and (_now_epoch() - heartbeat) < stale_seconds and not pid


def active_controller_issue(
    task_id: str,
    batch_id: str,
    *,
    current_pid: int | None = None,
    stale_seconds: int = DEFAULT_CONTROLLER_STALE_SECONDS,
) -> str | None:
    lease = read_controller_lease(task_id, batch_id)
    if not controller_lease_active(lease, current_pid=current_pid, stale_seconds=stale_seconds):
        return None
    owner = dict(lease or {})
    return (
        "GATE_BLOCK controller lease active for same task+batch: "
        f"controllerRunId={owner.get('controllerRunId')} pid={owner.get('pid')} "
        f"hostname={owner.get('hostname')} startedAt={owner.get('startedAt')}"
    )


@contextmanager
def controller_lease(
    task_id: str,
    batch_id: str,
    *,
    role: str = "batch_controller",
    stale_seconds: int = DEFAULT_CONTROLLER_STALE_SECONDS,
):
    """Acquire the only active controller lease for a task+batch."""

    try:
        import fcntl  # type: ignore
    except Exception:  # noqa: BLE001
        fcntl = None  # type: ignore

    lock_path = controller_lease_lock_path(task_id, batch_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = new_controller_run_id(task_id, batch_id)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                issue = active_controller_issue(task_id, batch_id, stale_seconds=stale_seconds)
                raise RuntimeError(
                    issue
                    or "GATE_BLOCK controller lease lock held for same task+batch; refusing to wait"
                ) from exc
        issue = active_controller_issue(task_id, batch_id, stale_seconds=stale_seconds)
        if issue:
            raise RuntimeError(issue)
        now = store.now_iso()
        lease = {
            "schemaVersion": CONTROLLER_LEASE_SCHEMA,
            "status": "active",
            "role": role,
            "taskId": task_id,
            "batchId": batch_id,
            "controllerRunId": run_id,
            "pid": os.getpid(),
            "pgid": os.getpgrp(),
            "hostname": socket.gethostname(),
            "startedAt": now,
            "heartbeatAt": now,
            "expiresAfterSeconds": stale_seconds,
        }
        write_json(controller_lease_path(task_id, batch_id, create=True), lease)
        try:
            yield lease
        finally:
            current = read_controller_lease(task_id, batch_id) or {}
            if str(current.get("controllerRunId") or "") == run_id:
                released = dict(current)
                released["status"] = "released"
                released["releasedAt"] = store.now_iso()
                released["heartbeatAt"] = released["releasedAt"]
                write_json(controller_lease_path(task_id, batch_id, create=True), released)


def heartbeat_controller_lease(task_id: str, batch_id: str, controller_run_id: str) -> None:
    lease = read_controller_lease(task_id, batch_id)
    if not lease or str(lease.get("controllerRunId") or "") != str(controller_run_id):
        return
    lease["heartbeatAt"] = store.now_iso()
    write_json(controller_lease_path(task_id, batch_id, create=True), lease)


def build_assignment(
    *,
    task_id: str,
    batch_id: str,
    controller_run_id: str,
    assignment_path: Sequence[str],
    role: str,
    scope: Mapping[str, Any],
    parent_assignment_id: str | None = None,
    allowed_read_roots: Sequence[str] | None = None,
    allowed_write_roots: Sequence[str] | None = None,
    budget: Mapping[str, Any] | None = None,
    deadline_epoch: float | None = None,
) -> dict[str, Any]:
    path = [str(item) for item in assignment_path if str(item).strip()]
    seed = f"{task_id}|{batch_id}|{controller_run_id}|{'/'.join(path)}|{role}|{json.dumps(dict(scope), sort_keys=True, ensure_ascii=False)}"
    assignment_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    now = store.now_iso()
    deadline = float(deadline_epoch) if deadline_epoch is not None else _now_epoch() + DEFAULT_ASSIGNMENT_DEADLINE_SECONDS
    return {
        "schemaVersion": ASSIGNMENT_SCHEMA,
        "assignmentId": assignment_id,
        "parentAssignmentId": parent_assignment_id,
        "taskId": task_id,
        "batchId": batch_id,
        "controllerRunId": controller_run_id,
        "assignmentPath": path,
        "role": role,
        "scope": dict(scope),
        "allowedReadRoots": [str(item) for item in (allowed_read_roots or [])],
        "allowedWriteRoots": [str(item) for item in (allowed_write_roots or [])],
        "budget": dict(budget or {}),
        "deadlineEpoch": deadline,
        "heartbeatAt": now,
        "createdAt": now,
    }


def _assignment_state(task_id: str, batch_id: str) -> dict[str, Any]:
    path = assignment_state_path(task_id, batch_id)
    if not path.is_file():
        return {
            "schemaVersion": ASSIGNMENT_STATE_SCHEMA,
            "taskId": task_id,
            "batchId": batch_id,
            "assignments": {},
        }
    data = read_json(path)
    if not isinstance(data, dict):
        return {
            "schemaVersion": ASSIGNMENT_STATE_SCHEMA,
            "taskId": task_id,
            "batchId": batch_id,
            "assignments": {},
        }
    data.setdefault("schemaVersion", ASSIGNMENT_STATE_SCHEMA)
    data.setdefault("taskId", task_id)
    data.setdefault("batchId", batch_id)
    if not isinstance(data.get("assignments"), dict):
        data["assignments"] = {}
    return data


def _assignment_semantic_fingerprint(row: Mapping[str, Any]) -> str:
    payload = {
        key: value
        for key, value in dict(row).items()
        if key not in {"createdAt", "updatedAt", "heartbeatAt", "deadlineEpoch", "eventType"}
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def append_assignment(task_id: str, batch_id: str, assignment: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(assignment)
    row.setdefault("schemaVersion", ASSIGNMENT_SCHEMA)
    now = store.now_iso()
    row.setdefault("heartbeatAt", now)
    row.setdefault("createdAt", now)
    state = _assignment_state(task_id, batch_id)
    assignments = state.setdefault("assignments", {})
    assignment_id = str(row.get("assignmentId") or "").strip()
    if not assignment_id:
        assignment_id = hashlib.sha1(
            json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        row["assignmentId"] = assignment_id
    existing = assignments.get(assignment_id) if isinstance(assignments, dict) else None
    row_fp = _assignment_semantic_fingerprint(row)
    existing_fp = (
        _assignment_semantic_fingerprint(existing)
        if isinstance(existing, Mapping)
        else ""
    )
    if isinstance(existing, Mapping) and row_fp == existing_fp:
        return dict(existing)
    event_type = "updated" if isinstance(existing, Mapping) else "created"
    persisted = dict(row)
    persisted["updatedAt"] = now
    if isinstance(existing, Mapping) and existing.get("createdAt"):
        persisted["createdAt"] = existing.get("createdAt")
    assignments[assignment_id] = persisted
    state["updatedAt"] = now
    write_json(assignment_state_path(task_id, batch_id), state)
    event = {
        "schemaVersion": ASSIGNMENT_EVENT_SCHEMA,
        "eventType": event_type,
        "recordedAt": now,
        **persisted,
    }
    _append_jsonl(assignment_events_path(task_id, batch_id), event)
    # Backward-compatible event stream for older audits.  It is now de-duplicated
    # and mirrors assignment_events.jsonl instead of logging every sync call.
    _append_jsonl(assignment_ledger_path(task_id, batch_id), event)
    return row


def validate_assignment_payload(payload: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if str(payload.get("assignmentId") or "").strip() == "":
        issues.append("assignmentId required")
    if str(payload.get("controllerRunId") or "").strip() == "":
        issues.append("controllerRunId required")
    if not isinstance(payload.get("assignmentPath"), list) or not payload.get("assignmentPath"):
        issues.append("assignmentPath required")
    if str(payload.get("role") or "").strip() == "":
        issues.append("role required")
    role = str(payload.get("role") or "").strip()
    if role and role not in {"supply_planner", "batch_controller"}:
        if str(payload.get("parentAssignmentId") or "").strip() == "":
            issues.append("parentAssignmentId required for delegated assignment")
    if not isinstance(payload.get("scope"), Mapping) or not payload.get("scope"):
        issues.append("scope required")
    if not isinstance(payload.get("budget"), Mapping) or not payload.get("budget"):
        issues.append("budget required")
    try:
        deadline_epoch = float(payload.get("deadlineEpoch") or 0)
    except (TypeError, ValueError):
        deadline_epoch = 0.0
    if deadline_epoch <= 0:
        issues.append("deadlineEpoch required")
    if str(payload.get("heartbeatAt") or "").strip() == "":
        issues.append("heartbeatAt required")
    for key in ("allowedReadRoots", "allowedWriteRoots"):
        if key in payload and not isinstance(payload.get(key), list):
            issues.append(f"{key} must be list")
    return issues


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return payload


def classify_failure(reason: object) -> str:
    text = str(reason or "").casefold()
    if any(
        marker in text
        for marker in (
            "cursor",
            "bridge",
            "sdk",
            "network",
            "timeout",
            "lease",
            "connection",
            "startup",
            "internal error",
        )
    ):
        return FAILURE_INFRA_RETRY
    if any(marker in text for marker in ("source", "fetch", "download", "candidate", "base draft", "sourcedraft")):
        return FAILURE_DATA_RETRY
    if any(marker in text for marker in ("duplicate", "conflict", "owner", "reuse", "mismatch")):
        return FAILURE_CONFLICT
    if any(marker in text for marker in ("blocked", "gate_block", "multi controller", "controller lease", "unauthorized", "cross-source")):
        return FAILURE_GATE_BLOCK
    if any(marker in text for marker in ("rights", "unsafe", "non-work", "abandoned", "weak match", "blocked source")):
        return FAILURE_ABANDON
    if any(marker in text for marker in ("review", "quality", "fact", "template", "image reference", "mechanical")):
        return FAILURE_QUALITY_REPAIR
    if any(marker in text for marker in ("human", "manual")):
        return FAILURE_MANUAL_REVIEW
    return FAILURE_QUALITY_REPAIR


def append_failure(
    task_id: str,
    batch_id: str,
    *,
    ref: str,
    stage: str,
    reason: str,
    category: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    failure_category = category or classify_failure(reason)
    if failure_category not in FINAL_FAILURE_CATEGORIES:
        failure_category = FAILURE_MANUAL_REVIEW
    return _append_jsonl(
        failure_ledger_path(task_id, batch_id),
        {
            "schemaVersion": FAILURE_LEDGER_SCHEMA,
            "taskId": task_id,
            "batchId": batch_id,
            "ref": ref,
            "stage": stage,
            "category": failure_category,
            "reason": reason,
            "owner": owner,
            "recordedAt": store.now_iso(),
        },
    )


def append_conflict(
    task_id: str,
    batch_id: str,
    *,
    conflict_type: str,
    subject: str,
    refs: Sequence[str] | None = None,
    reason: str = "",
    severity: str = "review_after_batch",
) -> dict[str, Any]:
    return _append_jsonl(
        conflict_ledger_path(task_id, batch_id),
        {
            "schemaVersion": CONFLICT_LEDGER_SCHEMA,
            "taskId": task_id,
            "batchId": batch_id,
            "conflictType": conflict_type,
            "subject": subject,
            "refs": [str(ref) for ref in (refs or [])],
            "reason": reason,
            "severity": severity,
            "status": "pending_reconcile",
            "recordedAt": store.now_iso(),
        },
    )


def source_unit_id(
    *,
    canonical_url: str = "",
    snapshot_hash: str = "",
    source_ref: str = "",
    entity_name: str = "",
    source_kind: str = "",
) -> str:
    """sourceUnitId（= sources/ 目录名）。

    可读契约（pipeline_directory_layout_spec §3）：提供 entity_name + source_kind 时
    返回 `{实体名}__{sourceKind}__{hash8}`（实体名保留中文，仅替换路径危险字符）。
    hash8 由 canonical URL / snapshot hash / source ref 稳定派生，跨批可复算。
    未提供实体语境（如 fanout job 标识）时回退纯哈希 `su_{hash20}`。
    """
    seed = f"{canonical_url.strip()}|{snapshot_hash.strip()}|{source_ref.strip()}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    name = str(entity_name or "").strip()
    kind = str(source_kind or "").strip()
    if name and kind:
        safe_name = re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("_.") or "entity"
        safe_kind = re.sub(r"[^a-zA-Z0-9_\-]+", "_", kind).strip("_") or "web"
        return f"{safe_name}__{safe_kind}__{digest[:8]}"
    return "su_" + digest[:20]


def source_unit_root_from_ref(ref: object) -> str:
    text = str(ref or "").replace("\\", "/").strip()
    if not text:
        return ""
    if "/assets/" in text:
        return text.split("/assets/", 1)[0]
    if text.endswith("/source.md") or text.endswith("/source.clean.md"):
        return text.rsplit("/", 1)[0]
    if "/sources/" in text:
        parts = text.split("/")
        try:
            idx = parts.index("sources")
            if len(parts) > idx + 1:
                return "/".join(parts[: idx + 2])
        except ValueError:
            pass
    return text.rsplit("/", 1)[0] if "/" in text else text


def source_unit_atomicity_issues(
    *,
    base_source_ref: object,
    asset_refs: Iterable[object] | None = None,
    supporting_refs: Iterable[object] | None = None,
) -> list[str]:
    base_root = source_unit_root_from_ref(base_source_ref)
    issues: list[str] = []
    if not base_root:
        return issues
    for label, refs in (("assetRefs", asset_refs or []), ("supportingRefs", supporting_refs or [])):
        for ref in refs:
            root = source_unit_root_from_ref(ref)
            if root and root != base_root:
                issues.append(
                    f"{label} must stay in same sourceUnit as baseSourceRef: base={base_root} got={root} ref={ref}"
                )
    return issues


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def summarize_failure_ledger(task_id: str, batch_id: str) -> dict[str, Any]:
    rows = read_jsonl(failure_ledger_path(task_id, batch_id))
    by_category: dict[str, int] = {}
    abandoned_by_reason: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category") or FAILURE_MANUAL_REVIEW)
        by_category[category] = by_category.get(category, 0) + 1
        if category == FAILURE_ABANDON:
            reason = str(row.get("reason") or "unknown").strip() or "unknown"
            abandoned_by_reason[reason] = abandoned_by_reason.get(reason, 0) + 1
    return {
        "totalFailures": len(rows),
        "byCategory": dict(sorted(by_category.items())),
        "abandonedByReason": dict(sorted(abandoned_by_reason.items())),
    }


def summarize_conflict_ledger(task_id: str, batch_id: str) -> dict[str, Any]:
    rows = read_jsonl(conflict_ledger_path(task_id, batch_id))
    by_type: dict[str, int] = {}
    pending = 0
    for row in rows:
        conflict_type = str(row.get("conflictType") or "unknown")
        by_type[conflict_type] = by_type.get(conflict_type, 0) + 1
        if str(row.get("status") or "") == "pending_reconcile":
            pending += 1
    return {
        "totalConflicts": len(rows),
        "pendingReconcile": pending,
        "byType": dict(sorted(by_type.items())),
    }


def target_scale_decision(rate: float) -> str:
    value = float(rate or 0.0)
    if value >= 0.9:
        return "promote_to_next_scale_plan"
    if value >= 0.75:
        return "rerun_same_scale_optimize_sources"
    return "replan_entry_scope_candidates_or_slicing"


def write_quality_target_report(
    task_id: str,
    batch_id: str,
    *,
    target_goal: int,
    quality_passed_count: int,
    abandoned_by_reason: Mapping[str, int] | None = None,
    conflicts_by_type: Mapping[str, int] | None = None,
    blockers: Sequence[str] | None = None,
) -> dict[str, Any]:
    failure_summary = summarize_failure_ledger(task_id, batch_id)
    conflict_summary = summarize_conflict_ledger(task_id, batch_id)
    goal = max(1, int(target_goal or 1))
    passed = max(0, int(quality_passed_count or 0))
    rate = round(passed / goal, 4)
    report = {
        "schemaVersion": QUALITY_TARGET_REPORT_SCHEMA,
        "taskId": task_id,
        "batchId": batch_id,
        "targetGoal": goal,
        "qualityPassedObjectCount": passed,
        "targetSatisfactionRate": rate,
        "scaleDecision": target_scale_decision(rate),
        "failureSummary": failure_summary,
        "conflictSummary": conflict_summary,
        "abandonedByReason": dict(abandoned_by_reason or failure_summary.get("abandonedByReason") or {}),
        "conflictsByType": dict(conflicts_by_type or conflict_summary.get("byType") or {}),
        "blockers": [str(item) for item in (blockers or [])],
        "recordedAt": store.now_iso(),
    }
    write_json(quality_target_report_path(task_id, batch_id), report)
    return report
