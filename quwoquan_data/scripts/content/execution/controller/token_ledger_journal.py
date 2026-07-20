"""Cursor 用量事件到批次 TokenLedger 的增量持久化。"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Mapping

from content.execution.workspace import execution_root
from core.io import read_json, write_json


def _ledger_path(execution_id: str) -> Path:
    return execution_root(execution_id) / "_shared" / "token_ledger.json"


@contextmanager
def _ledger_lock(execution_id: str) -> Iterator[None]:
    lock_path = (
        execution_root(execution_id)
        / "_shared"
        / ".token_ledger.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _current_ledger(execution_id: str) -> dict[str, object]:
    path = _ledger_path(execution_id)
    if path.is_file():
        payload = read_json(path)
        if not isinstance(payload, Mapping):
            raise ValueError("token ledger must be an object")
        if payload.get("executionId") not in {None, execution_id}:
            raise ValueError("token ledger executionId drift")
        return dict(payload)
    return {
        "schema": "quwoquan.token_ledger_batch",
        "executionId": execution_id,
        "measurementMode": "cursor_sdk_result_usage",
        "entries": [],
        "summary": {},
    }


def persist_cursor_usage_journal(
    *,
    execution_id: str,
    invocation_id: str,
    scope: str,
    content_object_ref: str,
    execution_stage: str,
    resolved_model_id: str,
    pricing_revision: str,
    status: str,
    turn_count: int,
    aggregate: Mapping[str, object],
    updated_at: str,
) -> None:
    """原子 upsert 一次调用；失败、取消和未知成本也不得丢失。"""
    if scope not in {"execution_stage", "content_object"}:
        raise ValueError(f"invalid Cursor usage scope: {scope}")
    with _ledger_lock(execution_id):
        payload = _current_ledger(execution_id)
        journal = payload.get("usageJournal")
        rows = dict(journal) if isinstance(journal, Mapping) else {}
        rows[invocation_id] = {
            "invocationId": invocation_id,
            "scope": scope,
            "contentObjectRef": content_object_ref or None,
            "executionStage": execution_stage or None,
            "resolvedModelId": resolved_model_id,
            "pricingRevision": pricing_revision or None,
            "status": status,
            "turnCount": turn_count,
            "aggregate": dict(aggregate),
            "updatedAt": updated_at,
        }
        payload["usageJournal"] = rows
        write_json(_ledger_path(execution_id), payload)


def existing_usage_journal(execution_id: str) -> dict[str, object]:
    """终态账本重建时保留逐 turn 审计链。"""
    path = _ledger_path(execution_id)
    if not path.is_file():
        return {}
    payload = read_json(path)
    journal = payload.get("usageJournal") if isinstance(payload, Mapping) else None
    return dict(journal) if isinstance(journal, Mapping) else {}


__all__ = ["existing_usage_journal", "persist_cursor_usage_journal"]
