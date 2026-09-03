"""Persistent local-readiness worker and inspection surfaces."""
from __future__ import annotations

import datetime as dt
import stat
import time
from pathlib import Path
from typing import Any

from . import core as _core
from . import queue as _queue


def _eligible(item: dict[str, Any], now: dt.datetime, debounce: float) -> bool:
    if item["terminal"] is not None:
        return False
    enqueued = _queue._parse_time(item["enqueued_at"], label="queue enqueued_at")
    eligible = _queue._parse_time(item["next_eligible_at"], label="queue next_eligible_at")
    return (now - enqueued).total_seconds() >= debounce and now >= eligible


def _worker_limits(contract: dict[str, Any]) -> tuple[int, float]:
    worker = contract.get("worker", {})
    maximum = worker.get("max_items_per_run", 8)
    budget = worker.get("wall_clock_budget_seconds", 120)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not (1 <= maximum <= 1000):
        raise _core.LocalReadinessError("worker max_items_per_run 非法")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not (0 < float(budget) <= 86400):
        raise _core.LocalReadinessError("worker wall_clock_budget_seconds 非法")
    return maximum, float(budget)


def _ordered(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (_queue._parse_time(item["enqueued_at"], label="queue enqueued_at"), str(item["path"]).encode("utf-8")))


def _worker_result(
    *,
    status: str,
    processed: list[str],
    remaining: list[dict[str, Any]],
    failures: list[str] | None = None,
    budget_exhausted: bool = False,
) -> dict[str, Any]:
    terminal = [item for item in remaining if item["terminal"] is not None]
    return {
        "schema": "local-readiness-worker-result-v2",
        "status": status,
        "processed": processed,
        "failed": failures or [],
        "pending": len(remaining) - len(terminal),
        "dead_letter": [item["path"] for item in terminal],
        "budget_exhausted": budget_exhausted,
    }


def worker_once(*, state_root: Path | None = None, debounce_seconds: float | None = None) -> dict[str, Any]:
    root = _core._state_root(state_root)
    contract = _core._load_contract()
    debounce = float(contract.get("worker", {}).get("debounce_seconds", 2) if debounce_seconds is None else debounce_seconds)
    max_items, wall_clock_budget = _worker_limits(contract)
    with _core.resource_lock("worker", state_root=root, wait=False):
        items = _core._queue_items(state_root=root)
        if not items:
            return _worker_result(status="IDLE", processed=[], remaining=[])
        now = dt.datetime.now(dt.timezone.utc)
        eligible = _ordered([item for item in items if _eligible(item, now, debounce)])
        terminal = [item for item in items if item["terminal"] is not None]
        if not eligible:
            result = _worker_result(
                status="GATE_BLOCK" if terminal else "BACKING_OFF",
                processed=[],
                remaining=items,
            )
            _core._atomic_json(root / "process/worker-last-result.json", result)
            return result

        processed: list[str] = []
        failures: list[str] = []
        started = time.monotonic()
        budget_exhausted = False
        scheduled = eligible[:max_items]
        for item in scheduled:
            remaining_budget = wall_clock_budget - (time.monotonic() - started)
            if remaining_budget <= 0:
                budget_exhausted = True
                break
            path = str(item["path"])
            processed.append(path)
            try:
                current_digest = _queue.path_queue_digest(path)
                if current_digest != item["input_digest"]:
                    raise _core.LocalReadinessError(f"queue source identity changed: {path}")
                plan = _core.plan_readiness(level="fast", paths=[path], repo_root=_core.ROOT, mode="workspace", state_root=root)
                check_identity = _core.canonical_digest(plan["checks"])
                bound = _queue.bind_queue_identity(
                    path=path,
                    input_digest=item["input_digest"],
                    evidence_fingerprint_ref=plan["fingerprint"]["ref"],
                    check_identity_digest=check_identity,
                    state_root=root,
                )
                if bound["terminal"] is not None:
                    failures.append(path)
                    continue
                remaining_budget = wall_clock_budget - (time.monotonic() - started)
                if remaining_budget <= 0:
                    processed.pop()
                    budget_exhausted = True
                    break
                receipt = _core.run_readiness(
                    plan, repo_root=_core.ROOT, state_root=root,
                    wall_clock_budget_seconds=remaining_budget,
                )
                if receipt.get("status") != "PASS":
                    failed = next((check for check in receipt.get("checks", []) if check.get("status") != "PASS"), {})
                    raise _core.LocalReadinessError(f"readiness check failed: {failed.get('id', 'unknown')} exit={failed.get('exit_code', 'unknown')}")
                outstanding = {queued.get("path") for queued in _core._queue_items(state_root=root)}
                if path in outstanding:
                    raise _core.LocalReadinessError("worker PASS 后 exact queue item 未消费")
            except (_core.LocalReadinessError, OSError, ValueError) as exc:
                failures.append(path)
                error_digest = _core.canonical_digest({"type": type(exc).__name__, "detail": str(exc)})
                try:
                    _queue.record_queue_failure(
                        path=path,
                        input_digest=item["input_digest"],
                        error_digest=error_digest,
                        state_root=root,
                    )
                except _core.LocalReadinessError as queue_exc:
                    # Source replacement is itself a stable typed terminal; enqueueing the
                    # current bytes resets retry metadata without reporting green.
                    _core.enqueue_paths([path], reason="source_identity_changed", state_root=root)
                    replacement = next(value for value in _core._queue_items(state_root=root) if value["path"] == path)
                    _queue.record_queue_failure(
                        path=path,
                        input_digest=replacement["input_digest"],
                        error_digest=_core.canonical_digest({"type": type(queue_exc).__name__, "detail": str(queue_exc)}),
                        state_root=root,
                    )

            if time.monotonic() - started >= wall_clock_budget:
                budget_exhausted = True

        if len(eligible) > len(scheduled):
            budget_exhausted = True
        remaining = _core._queue_items(state_root=root)
        terminal = [item for item in remaining if item["terminal"] is not None]
        if terminal:
            status = "GATE_BLOCK"
        elif failures or remaining:
            status = "PENDING"
        else:
            status = "PASS"
        result = _worker_result(
            status=status,
            processed=processed,
            remaining=remaining,
            failures=failures,
            budget_exhausted=budget_exhausted,
        )
        _core._atomic_json(root / "process/worker-last-result.json", result)
        return result


def _worker_running(root: Path) -> int:
    try:
        with _core.resource_lock("worker", state_root=root, wait=False):
            return 0
    except _core.LocalReadinessError as exc:
        if str(exc) == "resource busy: worker":
            return 1
        raise


def _queue_summary(items: list[dict[str, Any]], now: dt.datetime, *, running_count: int) -> dict[str, Any]:
    pending = [item for item in items if item["terminal"] is None]
    failed = [item for item in pending if item["attempt_count"] > 0]
    stale = [item for item in pending if _queue.path_queue_digest(str(item["path"])) != item["input_digest"]]
    ordered = _ordered(items)
    oldest_enqueued_at = ordered[0]["enqueued_at"] if ordered else None
    oldest_age_seconds = None
    if oldest_enqueued_at is not None:
        oldest = _queue._parse_time(oldest_enqueued_at, label="queue enqueued_at")
        oldest_age_seconds = max(0, int((now - oldest).total_seconds()))
    eligible = [item for item in pending if _eligible(item, now, 0)]
    return {
        "backlog_count": len(items),
        "pending_count": len(pending),
        "running_count": running_count,
        "stale_count": len(stale),
        "failed_count": len(failed),
        "dead_letter_count": len(items) - len(pending),
        "eligible_count": len(eligible),
        "oldest_enqueued_at": oldest_enqueued_at,
        "oldest_age_seconds": oldest_age_seconds,
    }


def inspect_state(*, state_root: Path | None = None) -> dict[str, Any]:
    root = _core._state_root(state_root)
    queue_path = root / "process/deferred-queue.json"
    queue = _core._read_queue(queue_path) or {"schema": "local-readiness-queue-v2", "items": []}
    dead_letter = [item for item in queue["items"] if item["terminal"] is not None]
    pending = [item for item in queue["items"] if item["terminal"] is None]
    worker_path = root / "process/worker-last-result.json"
    worker: Any = {"status": "NEVER_RUN"}
    if _core._regular_file_exists(worker_path, label="local readiness worker result"):
        worker = _core._read_json_regular(worker_path, label="local readiness worker result")
        if not isinstance(worker, dict):
            raise _core.LocalReadinessError("local readiness worker result 必须为 object")
    pointers: dict[str, Any] = {}
    pointer_root = root / "process/receipts/current"
    try:
        pointer_metadata = pointer_root.lstat()
    except FileNotFoundError:
        pointer_metadata = None
    if pointer_metadata is not None:
        if not stat.S_ISDIR(pointer_metadata.st_mode):
            raise _core.LocalReadinessError("readiness current pointer root 必须为 directory 且不得为 symlink")
        _core._reject_symlink_components(pointer_root, label="readiness current pointer root")
        for path in sorted(pointer_root.glob("*.json")):
            _core._canonical_receipt_from_pointer(path, state_root=root)
            pointers[path.stem] = _core._read_json_regular(path, label="readiness current pointer")
    readiness = "ADVISORY" if queue["items"] else "IDLE"
    summary = _queue_summary(
        queue["items"],
        dt.datetime.now(dt.timezone.utc),
        running_count=_worker_running(root),
    )
    return {
        "schema": "local-readiness-inspection-v2",
        "readiness": readiness,
        "queue_closure": _queue.inspect_queue_closure(queue["items"]),
        **summary,
        "summary": summary,
        "queue": queue,
        "pending": pending,
        "dead_letter": dead_letter,
        "worker": worker,
        "receipt_pointers": pointers,
    }
