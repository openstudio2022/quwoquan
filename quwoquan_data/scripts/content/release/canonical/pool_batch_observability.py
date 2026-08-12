"""Derive per-task supply funnel statistics from existing canonical evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import (
    is_pool_record_admitted,
    latest_pool_record,
)
from content.release.canonical.object_transaction_contract import _read_json


def _instant(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_ms(start: object, end: object) -> int | None:
    first = _instant(start)
    last = _instant(end)
    if first is None or last is None or last < first:
        return None
    return int((last - first).total_seconds() * 1000)


def _task_runtime(output_root: Path, task_id: str) -> tuple[int | None, int | None, list[dict[str, Any]]]:
    root = output_root / "data" / "tasks" / task_id
    request_path = root / "0.plan" / "request.json"
    request = _read_json(request_path) if request_path.is_file() else {}
    target = request.get("quota")
    if not isinstance(target, int) or isinstance(target, bool) or target < 0:
        target = None

    state_path = root / "_shared" / "execution_state.json"
    state = _read_json(state_path) if state_path.is_file() else {}
    duration = _duration_ms(state.get("startedAt"), state.get("updatedAt"))

    completed_at: dict[str, datetime] = {}
    for path in sorted((root / "_shared" / "execution_state_events").glob("*.json")):
        event = _read_json(path)
        instant = _instant(event.get("createdAt"))
        delta = event.get("stateDelta")
        changed = delta.get("set") if isinstance(delta, Mapping) else None
        completed = changed.get("completed") if isinstance(changed, Mapping) else None
        if instant is None or not isinstance(completed, list):
            continue
        for raw_stage in completed:
            stage = str(raw_stage or "").strip()
            if stage and stage not in completed_at:
                completed_at[stage] = instant
    stage_rows: list[dict[str, Any]] = []
    previous = _instant(state.get("startedAt"))
    for stage, instant in sorted(completed_at.items(), key=lambda item: item[1]):
        if previous is not None and instant >= previous:
            stage_rows.append(
                {
                    "name": stage,
                    "durationMs": int((instant - previous).total_seconds() * 1000),
                }
            )
        previous = instant
    return target, duration, stage_rows


def _manifest_rows(publish_root: Path) -> list[tuple[str, Path, Mapping[str, Any], str]]:
    rows: list[tuple[str, Path, Mapping[str, Any], str]] = []
    for kind, object_type in (("entities", "homepage"), ("posts", "content")):
        root = publish_root / kind
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("manifest.json")):
            ref = f"{kind}/{path.parent.relative_to(root).as_posix()}"
            rows.append((ref, path.parent, _read_json(path), object_type))
    return rows


def build_batch_statistics(
    *,
    publish_root: Path,
    output_root: Path,
    issues: Sequence[Mapping[str, str]],
    pending_delivery: Sequence[Mapping[str, Any]] = (),
    execution_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Return statistics only; no field in this result participates in admission."""

    issue_refs = {
        str(row.get("ref") or "").split(":", 1)[0] for row in issues
    }
    exact_execution_ids = {str(value) for value in execution_ids}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ref, root, manifest, object_type in _manifest_rows(publish_root):
        task_id = str(
            manifest.get("sourceTaskId") or manifest.get("executionId") or ""
        ).strip()
        if task_id not in exact_execution_ids:
            continue
        if not task_id:
            task_id = f"unattributed:{ref}"
        record = latest_pool_record(root, object_type)
        admitted = is_pool_record_admitted(record)
        scope = str(record.get("usageScope") or "unknown") if record else "unknown"
        if scope not in {"research", "commercial"}:
            scope = "unknown"
        grouped[task_id].append(
            {
                "qualityPassed": bool(record and record.get("qualityResult") == "passed"),
                "scope": scope,
                "admitted": admitted,
                "publishable": admitted and ref not in issue_refs,
                "deliveryPending": admitted and ref in issue_refs,
            }
        )

    for intent in pending_delivery:
        task_id = str(intent.get("executionId") or "").strip()
        if not task_id or task_id not in exact_execution_ids:
            continue
        grouped[task_id].append(
            {
                "qualityPassed": True,
                "scope": "unknown",
                "admitted": False,
                "publishable": False,
                "deliveryPending": True,
            }
        )

    result: list[dict[str, Any]] = []
    for task_id in sorted(grouped):
        rows = grouped[task_id]
        quality = Counter("passed" if row["qualityPassed"] else "failed" for row in rows)
        scopes = Counter(str(row["scope"]) for row in rows)
        admitted = sum(bool(row["admitted"]) for row in rows)
        publishable = sum(bool(row["publishable"]) for row in rows)
        target, duration, stages = _task_runtime(output_root, task_id)
        generated = len(rows)
        delivery_pending = sum(bool(row["deliveryPending"]) for row in rows)
        excluded = sum(
            not row["admitted"] and not row["deliveryPending"] for row in rows
        )
        result.append(
            {
                "sourceTaskId": task_id,
                "target": target,
                "generated": generated,
                "quality": {"passed": quality["passed"], "failed": quality["failed"]},
                "usageScope": {
                    "research": scopes["research"],
                    "commercial": scopes["commercial"],
                    "unknown": scopes["unknown"],
                },
                "admitted": admitted,
                "publishable": publishable,
                "deliveryPending": delivery_pending,
                "excluded": excluded,
                "successRate": round(publishable / generated, 6) if generated else 0.0,
                "durationMs": duration,
                "stages": stages,
            }
        )
    return result


__all__ = ["build_batch_statistics"]
