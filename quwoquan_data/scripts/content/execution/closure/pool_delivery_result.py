"""Canonical deterministic pool-delivery result projection and create-once writer."""
from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.execution.identity import validate_execution_id
from content.execution.runtime_contract import canonical_sha256
from core.control_types import RecoveryNextAction
from core.schema import assert_valid

_TERMINAL_RESULTS = frozenset({"appended", "replayed"})
_HOST_MODES = frozenset({"host_publish", "frozen_publish_jobs", "reviewed_delivery_only", "campaign_reviewed_publish"})


def _batch_digest(intent_ids: Sequence[str | None]) -> str:
    return canonical_sha256(sorted({str(value) for value in intent_ids if value}))


def build_pool_delivery_object_result(*, execution_id: str, object_ref: str, intent_id: str | None, result: str, canonical_object: Mapping[str, Any] | None = None, issue_codes: Sequence[str] = (), next_action: RecoveryNextAction = RecoveryNextAction.NONE) -> dict[str, Any]:
    normalized = validate_execution_id(execution_id)
    settled = result in _TERMINAL_RESULTS and canonical_object is not None
    closure_digest = str(canonical_object["objectClosureDigest"]) if settled else ""
    own_intents = [intent_id] if intent_id else []
    reentry = {"executionId": normalized, "batchInputDigest": _batch_digest(own_intents), "intentIds": own_intents}
    return {"objectRef": object_ref, "intentId": intent_id, "transactionInputDigest": closure_digest if closure_digest.startswith("sha256:") else None, "result": result, "canonicalObject": dict(canonical_object) if settled else None, "issueCodes": [] if settled else sorted(set(issue_codes)), "nextAction": RecoveryNextAction.NONE.value if settled else next_action.value, "reentryRef": None if settled else reentry}


def build_pool_delivery_drain_result(*, execution_id: str, recovery_mode: str, object_results: Sequence[Mapping[str, Any]], issue_codes: Sequence[str] = ()) -> dict[str, Any]:
    normalized = validate_execution_id(execution_id)
    if recovery_mode not in _HOST_MODES:
        raise ValueError(f"pool delivery host mode is invalid: {recovery_mode}")
    rows = [dict(row) for row in object_results]
    by_result = Counter(str(row["result"]) for row in rows)
    pending = by_result["pending"]
    blocked = by_result["blocked"]
    settled_rows = [row for row in rows if str(row["result"]) in _TERMINAL_RESULTS]
    canonical_objects = [dict(row["canonicalObject"]) for row in settled_rows if isinstance(row.get("canonicalObject"), Mapping)]
    intent_ids = sorted({str(row["intentId"]) for row in rows if row.get("intentId")})
    batch_input_digest = _batch_digest(intent_ids)
    status = "waiting" if pending else "blocked" if blocked else "completed"
    unsettled_actions = [str(row["nextAction"]) for row in rows if row.get("reentryRef") is not None]
    next_action = RecoveryNextAction.NONE.value if status == "completed" else (unsettled_actions[0] if unsettled_actions else RecoveryNextAction.RESUME_DELIVERY.value)
    report = {"schema": "quwoquan_data.pool_delivery_drain_result", "executionId": normalized, "recoveryMode": recovery_mode, "executionStatePreserved": True, "status": status, "attemptedCount": len(rows) - by_result["excluded"], "completedCount": len(settled_rows), "qualifiedCount": len(rows) - by_result["excluded"], "discardedCount": by_result["excluded"] + blocked, "total": len(rows), "appendedCount": by_result["appended"], "replayedCount": by_result["replayed"], "pendingCount": pending, "excludedCount": by_result["excluded"], "blockedCount": blocked, "poolDelta": by_result["appended"], "batchInputDigest": batch_input_digest, "recordSetDigest": canonical_sha256([dict(row["poolRecord"]) for row in canonical_objects if isinstance(row.get("poolRecord"), Mapping)]), "objectResults": rows, "intentIds": intent_ids, "canonicalObjects": canonical_objects, "issueCodes": sorted({*(str(code) for code in issue_codes if str(code).strip()), *(str(code) for row in rows for code in row.get("issueCodes") or () if str(code).strip())}), "nextAction": next_action, "reentryRef": {"executionId": normalized, "batchInputDigest": batch_input_digest, "intentIds": intent_ids}}
    assert_valid(report, "execution", "pool_delivery_drain_result", label=f"pool delivery result:{normalized}")
    return report


def write_pool_delivery_result_create_once(*, path: Path, result: Mapping[str, Any]) -> Path:
    document = dict(result)
    assert_valid(document, "execution", "pool_delivery_drain_result", label="pool delivery result")
    encoded = (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        if destination.is_symlink() or destination.read_bytes() != encoded:
            raise ValueError("DATA.POOL.DELIVERY_RESULT_CREATE_ONCE_CONFLICT") from None
        return destination
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return destination


__all__ = ["build_pool_delivery_drain_result", "build_pool_delivery_object_result", "write_pool_delivery_result_create_once"]
