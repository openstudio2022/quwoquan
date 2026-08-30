"""Persistent exact-input queue with bounded retry and dead-letter semantics."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from . import core as _core

_QUEUE_FIELDS = (
    "id",
    "path",
    "scopes",
    "input_digest",
    "reason",
    "enqueued_at",
    "attempt_count",
    "max_attempts",
    "next_eligible_at",
    "last_error_digest",
    "terminal",
    "evidence_fingerprint_ref",
    "check_identity_digest",
)
_TERMINAL_FIELDS = ("status", "code", "at", "error_digest")


def _parse_time(value: str, *, label: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise _core.LocalReadinessError(f"{label} 非法") from exc
    if parsed.tzinfo is None:
        raise _core.LocalReadinessError(f"{label} 必须含 timezone")
    return parsed.astimezone(dt.timezone.utc)


def queue_control_paths(*, state_root: Path | None = None) -> list[str]:
    root = _core._state_root(state_root)
    try:
        relative = root.relative_to(_core._canonical_absolute(_core.ROOT))
    except ValueError:
        return []
    return [relative.as_posix()]


def path_queue_digest(path: str) -> str:
    return _core.canonical_digest(_core.workspace_digests([path], repo_root=_core.ROOT))


def _new_item(path: str, *, digest: str, reason: str, max_attempts: int) -> dict[str, Any]:
    now = _core._utc_now()
    return {
        "id": _core.canonical_digest({"path": path, "input_digest": digest}),
        "path": path,
        "scopes": _core.classify_scopes([path]) or ["spec_contract"],
        "input_digest": digest,
        "reason": reason,
        "enqueued_at": now,
        "attempt_count": 0,
        "max_attempts": max_attempts,
        "next_eligible_at": now,
        "last_error_digest": None,
        "terminal": None,
        "evidence_fingerprint_ref": None,
        "check_identity_digest": None,
    }


def validate_queue(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema", "items"}:
        raise _core.LocalReadinessError("deferred queue exact schema 非法")
    if value.get("schema") != "local-readiness-queue-v2" or not isinstance(value.get("items"), list):
        raise _core.LocalReadinessError("deferred queue schema 非法")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value["items"]:
        if not isinstance(item, dict) or set(item) != set(_QUEUE_FIELDS):
            raise _core.LocalReadinessError("deferred queue item exact schema 非法")
        path, scopes = item.get("path"), item.get("scopes")
        terminal = item.get("terminal")
        if (
            not isinstance(item.get("id"), str)
            or not isinstance(path, str)
            or not isinstance(scopes, list)
            or not scopes
            or not all(isinstance(scope, str) and scope for scope in scopes)
            or not isinstance(item.get("input_digest"), str)
            or not isinstance(item.get("reason"), str)
            or not isinstance(item.get("enqueued_at"), str)
            or isinstance(item.get("attempt_count"), bool)
            or not isinstance(item.get("attempt_count"), int)
            or isinstance(item.get("max_attempts"), bool)
            or not isinstance(item.get("max_attempts"), int)
            or item["attempt_count"] < 0
            or item["max_attempts"] < 1
            or item["attempt_count"] > item["max_attempts"]
            or not isinstance(item.get("next_eligible_at"), (str, type(None)))
            or not isinstance(item.get("last_error_digest"), (str, type(None)))
            or not isinstance(item.get("evidence_fingerprint_ref"), (str, type(None)))
            or not isinstance(item.get("check_identity_digest"), (str, type(None)))
        ):
            raise _core.LocalReadinessError("deferred queue item 字段类型非法")
        normalized = _core.normalize_repo_relative_path(path, _core.ROOT)
        if normalized != path or path in seen:
            raise _core.LocalReadinessError("deferred queue path 非 canonical 或重复")
        _parse_time(item["enqueued_at"], label="queue enqueued_at")
        if item["next_eligible_at"] is not None:
            _parse_time(item["next_eligible_at"], label="queue next_eligible_at")
        if terminal is not None:
            if not isinstance(terminal, dict) or set(terminal) != set(_TERMINAL_FIELDS):
                raise _core.LocalReadinessError("deferred queue terminal exact schema 非法")
            if (
                terminal.get("status") != "GATE_BLOCK"
                or terminal.get("code") not in {"LOCAL_READINESS.RETRY_EXHAUSTED", "LOCAL_READINESS.SOURCE_IDENTITY_DRIFT"}
                or not isinstance(terminal.get("at"), str)
                or not isinstance(terminal.get("error_digest"), str)
                or item["next_eligible_at"] is not None
            ):
                raise _core.LocalReadinessError("deferred queue terminal 字段非法")
            _parse_time(terminal["at"], label="queue terminal at")
        elif item["next_eligible_at"] is None:
            raise _core.LocalReadinessError("非 terminal queue item 必须有 next_eligible_at")
        expected_id = _core.canonical_digest({"path": path, "input_digest": item["input_digest"]})
        if item["id"] != expected_id:
            raise _core.LocalReadinessError("deferred queue item identity 漂移")
        seen.add(path)
        validated.append({field: item[field] for field in _QUEUE_FIELDS})
    return {"schema": "local-readiness-queue-v2", "items": validated}


def read_queue(path: Path) -> dict[str, Any] | None:
    if not _core._regular_file_exists(path, label="deferred queue"):
        return None
    value = _core._read_json_regular(path, label="deferred queue")
    if value == {"schema": "local-readiness-queue-v1", "items": []}:
        return {"schema": "local-readiness-queue-v2", "items": []}
    return validate_queue(value)


def enqueue_paths(paths: list[str], *, reason: str = "after_edit", state_root: Path | None = None) -> dict[str, Any]:
    root = _core._state_root(state_root)
    queue_path = root / "process/deferred-queue.json"
    normalized = sorted({_core.normalize_repo_relative_path(path, _core.ROOT) for path in paths})
    contract = _core._load_contract().get("worker", {})
    max_attempts = int(contract.get("max_attempts", 4))
    if max_attempts < 1 or max_attempts > 20:
        raise _core.LocalReadinessError("worker max_attempts 非法")
    with _core.resource_lock("queue", state_root=root):
        current = read_queue(queue_path) or {"schema": "local-readiness-queue-v2", "items": []}
        indexed = {item["path"]: item for item in current["items"]}
        for path in normalized:
            digest = path_queue_digest(path)
            existing = indexed.get(path)
            if existing is not None and existing["input_digest"] == digest:
                continue
            indexed[path] = _new_item(path, digest=digest, reason=reason, max_attempts=max_attempts)
        result = {"schema": "local-readiness-queue-v2", "items": sorted(indexed.values(), key=lambda item: item["path"])}
        _core._atomic_json(queue_path, result)
        return result


def queue_items(*, state_root: Path | None = None) -> list[dict[str, Any]]:
    value = read_queue(_core._state_root(state_root) / "process/deferred-queue.json")
    return [] if value is None else value["items"]


def bind_queue_identity(
    *,
    path: str,
    input_digest: str,
    evidence_fingerprint_ref: str,
    check_identity_digest: str,
    state_root: Path | None = None,
) -> dict[str, Any]:
    root = _core._state_root(state_root)
    queue_path = root / "process/deferred-queue.json"
    with _core.resource_lock("queue", state_root=root):
        value = read_queue(queue_path)
        if value is None:
            raise _core.LocalReadinessError(f"queue item disappeared before identity bind: {path}")
        selected: dict[str, Any] | None = None
        for item in value["items"]:
            if item["path"] != path:
                continue
            if item["input_digest"] != input_digest:
                raise _core.LocalReadinessError(f"queue input changed before identity bind: {path}")
            selected = item
            break
        if selected is None:
            raise _core.LocalReadinessError(f"queue item disappeared before identity bind: {path}")
        prior = (selected["evidence_fingerprint_ref"], selected["check_identity_digest"])
        current = (evidence_fingerprint_ref, check_identity_digest)
        if prior != (None, None) and prior != current:
            error_digest = _core.canonical_digest({"code": "LOCAL_READINESS.SOURCE_IDENTITY_DRIFT", "prior": prior, "current": current})
            selected["last_error_digest"] = error_digest
            selected["next_eligible_at"] = None
            selected["terminal"] = {
                "status": "GATE_BLOCK",
                "code": "LOCAL_READINESS.SOURCE_IDENTITY_DRIFT",
                "at": _core._utc_now(),
                "error_digest": error_digest,
            }
        else:
            selected["evidence_fingerprint_ref"] = evidence_fingerprint_ref
            selected["check_identity_digest"] = check_identity_digest
        _core._atomic_json(queue_path, value)
        return dict(selected)


def record_queue_failure(
    *,
    path: str,
    input_digest: str,
    error_digest: str,
    state_root: Path | None = None,
) -> dict[str, Any]:
    root = _core._state_root(state_root)
    queue_path = root / "process/deferred-queue.json"
    contract = _core._load_contract().get("worker", {})
    base = float(contract.get("retry_base_seconds", 2))
    maximum = float(contract.get("retry_max_seconds", 60))
    if not (0 < base <= maximum <= 3600):
        raise _core.LocalReadinessError("worker retry backoff contract 非法")
    with _core.resource_lock("queue", state_root=root):
        value = read_queue(queue_path)
        if value is None:
            raise _core.LocalReadinessError(f"queue item disappeared before failure record: {path}")
        selected: dict[str, Any] | None = None
        for item in value["items"]:
            if item["path"] == path:
                selected = item
                break
        if selected is None or selected["input_digest"] != input_digest:
            raise _core.LocalReadinessError(f"queue input changed before failure record: {path}")
        selected["attempt_count"] += 1
        selected["last_error_digest"] = error_digest
        now = dt.datetime.now(dt.timezone.utc)
        if selected["attempt_count"] >= selected["max_attempts"]:
            selected["next_eligible_at"] = None
            selected["terminal"] = {
                "status": "GATE_BLOCK",
                "code": "LOCAL_READINESS.RETRY_EXHAUSTED",
                "at": now.isoformat(timespec="seconds"),
                "error_digest": error_digest,
            }
        else:
            delay = min(maximum, base * (2 ** (selected["attempt_count"] - 1)))
            selected["next_eligible_at"] = (now + dt.timedelta(seconds=delay)).isoformat(timespec="seconds")
        _core._atomic_json(queue_path, value)
        return dict(selected)


def assert_scope_queue_closed(plan: dict[str, Any], *, state_root: Path | None = None) -> None:
    if plan["level"] == "fast":
        return
    covered, scopes = set(plan["paths"]), set(plan["scopes"])
    outstanding = sorted({item["path"] for item in queue_items(state_root=state_root) if set(item["scopes"]) & scopes and item["path"] not in covered})
    if outstanding:
        raise _core.LocalReadinessError(f"scope/release persistent queue 仍有相关范围 outstanding: {outstanding}")


def clear_queue_exact(paths: list[str], *, state_root: Path | None = None) -> None:
    root = _core._state_root(state_root)
    queue_path = root / "process/deferred-queue.json"
    current_digests = {path: path_queue_digest(path) for path in paths}
    with _core.resource_lock("queue", state_root=root):
        value = read_queue(queue_path)
        if value is None:
            return
        queued = {item["path"]: item for item in value["items"]}
        for path, digest in current_digests.items():
            if path in queued and queued[path]["input_digest"] != digest:
                raise _core.LocalReadinessError(f"queue input changed before clear: {path}")
        retained = [item for item in value["items"] if item["path"] not in current_digests]
        _core._atomic_json(queue_path, {"schema": "local-readiness-queue-v2", "items": retained})
