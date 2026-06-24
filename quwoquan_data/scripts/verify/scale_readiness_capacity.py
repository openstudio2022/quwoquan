"""Capacity and creator-load helpers for the scale-readiness gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.creator_assignment import (
    creator_assignment_issues,
    creator_assignment_required,
    creator_from_payload,
)
from _common.io import read_json


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def token_ledger_paths(root: Path) -> list[str]:
    names = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if "token" in lowered and "ledger" in lowered and path.suffix == ".json":
            names.append(str(path))
    return names


def creator_load_report(
    root: Path,
    spec: Mapping[str, Any],
    *,
    target_goal: int = 0,
) -> dict[str, Any]:
    packet = _load_json_if_exists(root / "_shared" / "content_plan_packet.json")
    items = packet.get("items") if isinstance(packet.get("items"), list) else []
    by_creator: dict[str, dict[str, Any]] = {}
    missing_assignments: list[str] = []
    assignment_issues: list[str] = []

    def row(creator_id: str) -> dict[str, Any]:
        return by_creator.setdefault(
            creator_id or "<missing>",
            {
                "planned": 0,
                "published": 0,
                "tokenLedgerEntries": 0,
                "objectTypes": {},
            },
        )

    for item in items:
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("ref") or "").strip()
        carrier = str(item.get("carrier") or item.get("contentType") or "article")
        creator = creator_from_payload(item)
        creator_id = str(creator.get("creatorProfileId") or "").strip()
        if not creator_id:
            missing_assignments.append(ref or f"item[{len(missing_assignments)}]")
        for issue in creator_assignment_issues(
            item,
            carrier="image" if carrier == "gallery" else carrier,
            prefix=f"item[{ref or '?'}].creatorAssignment",
        ):
            assignment_issues.append(issue)
        r = row(creator_id)
        r["planned"] += 1
        key = "image" if carrier == "gallery" else carrier
        r["objectTypes"][key] = int(r["objectTypes"].get(key, 0)) + 1

    posts_root = root / "posts"
    for manifest_path in (
        sorted(posts_root.rglob("manifest.json")) if posts_root.is_dir() else []
    ):
        manifest = _load_json_if_exists(manifest_path)
        creator_id = str(manifest.get("creatorProfileId") or "").strip()
        r = row(creator_id)
        r["published"] += 1

    for token_path in token_ledger_paths(root):
        ledger = _load_json_if_exists(Path(token_path))
        entries = ledger.get("entries") if isinstance(ledger.get("entries"), list) else []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            creator_id = str(entry.get("creatorProfileId") or "").strip()
            row(creator_id)["tokenLedgerEntries"] += 1

    active = [
        {"creatorProfileId": creator_id, **data}
        for creator_id, data in sorted(by_creator.items())
        if creator_id != "<missing>"
    ]
    max_planned = max((int(item.get("planned") or 0) for item in active), default=0)
    total_planned = sum(int(item.get("planned") or 0) for item in active)
    max_share = round(max_planned / total_planned, 4) if total_planned else 0.0
    max_daily_posts = 1
    overload = [
        item["creatorProfileId"]
        for item in active
        if int(item.get("planned") or 0) > max_daily_posts and target_goal >= 100
    ]
    return {
        "schemaVersion": "quwoquan_data.creator_load_report/1",
        "required": creator_assignment_required(spec),
        "creatorCount": len(active),
        "plannedObjectCount": total_planned,
        "publishedObjectCount": sum(int(item.get("published") or 0) for item in active),
        "maxPlannedPerCreator": max_planned,
        "maxCreatorShare": max_share,
        "maxDailyPostsPerCreator": max_daily_posts,
        "missingAssignmentRefs": missing_assignments[:50],
        "assignmentIssueCount": len(assignment_issues),
        "assignmentIssues": assignment_issues[:50],
        "overloadedCreatorProfileIds": overload[:50],
        "byCreator": active,
    }


def resolve_agent_active(
    measured_throughput: Mapping[str, Any] | None,
    state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve per-worker author metrics independent of run.py metric version."""
    agent_active: dict[str, Any] = {}
    if isinstance(measured_throughput, Mapping) and isinstance(
        measured_throughput.get("agentActive"), Mapping
    ):
        agent_active = dict(measured_throughput["agentActive"])
    if not agent_active.get("perWorkerObjectsPerHour") and isinstance(state, Mapping):
        try:
            from task.run import _agent_active_throughput

            recomputed = _agent_active_throughput(state)
            if isinstance(recomputed, Mapping) and recomputed.get("perWorkerObjectsPerHour"):
                agent_active = dict(recomputed)
        except Exception:
            pass
    return agent_active


def throughput_projection(
    agent_active: Mapping[str, Any] | None,
    *,
    queue_backend: str,
    max_concurrency: int,
    required_per_hour: float,
) -> dict[str, Any]:
    """Project daily author capacity from the trial's measured per-worker rate."""
    agent_active = dict(agent_active) if isinstance(agent_active, Mapping) else {}

    def _num(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    per_worker = _num(agent_active.get("perWorkerObjectsPerHour"))
    finished = int(_num(agent_active.get("finishedAuthorJobs")))
    active_seconds = _num(agent_active.get("authorActiveSeconds"))
    realized_workers = int(_num(agent_active.get("effectiveWorkerCount")))
    committed = max(0, int(max_concurrency or 0)) if queue_backend == "reliabletask" else 0
    has_evidence = per_worker > 0 and finished >= 1 and active_seconds > 0 and committed >= 1
    projected_per_hour = round(per_worker * committed, 4) if has_evidence else 0.0
    return {
        "available": bool(has_evidence),
        "measurementMode": "projected_from_trial_per_worker_rate",
        "perWorkerObjectsPerHour": round(per_worker, 4),
        "realizedWorkerCount": realized_workers,
        "committedConcurrency": committed,
        "queueBackend": queue_backend or "",
        "projectedObjectsPerHour": projected_per_hour,
        "projectedDailyCapacity": round(projected_per_hour * 24, 2),
        "requiredObjectsPerHour": round(required_per_hour, 4),
        "finishedAuthorJobs": finished,
        "authorActiveSeconds": round(active_seconds, 3),
        "assumptions": [
            "linear scaling of measured per-worker author throughput across committed reliabletask workers",
            "source supply and review keep pace with committed concurrency",
        ],
    }
