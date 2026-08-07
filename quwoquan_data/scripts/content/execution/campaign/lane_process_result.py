"""Typed terminal cause and process evidence for campaign lanes."""

from __future__ import annotations

import signal
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json


def _render_typed_terminal_cause(
    *,
    stage: str,
    message: object,
    issue_records: object,
) -> str | None:
    """Render the structured execution failure without parsing human log text."""

    parts: list[str] = []
    normalized_message = (
        " ".join(str(message).split()) if isinstance(message, str) else ""
    )
    if normalized_message:
        parts.append(normalized_message)
    records = issue_records if isinstance(issue_records, list) else []
    for raw in records[:5]:
        if not isinstance(raw, Mapping):
            continue
        code = str(raw.get("code") or "").strip()
        issue_message = " ".join(str(raw.get("message") or "").split())
        label = f"[{code}]" if code else "[typed issue]"
        if issue_message:
            label += f" {issue_message}"
        attributes = raw.get("attrs")
        details: list[str] = []
        if stage:
            details.append(f"stage={stage}")
        if isinstance(attributes, Mapping):
            details.extend(
                f"{key}={' '.join(str(value).split())}"
                for key, value in sorted(attributes.items())
                if str(key).strip() and str(value).strip()
            )
        if details:
            label += " (" + "; ".join(details) + ")"
        parts.append(label)
    rendered = "\n".join(dict.fromkeys(parts)).strip()
    return rendered[:2400] if rendered else None


def typed_execution_terminal_cause(
    execution_root: Path,
    *,
    execution_id: str,
) -> str | None:
    """Prefer durable execution state/packet evidence over buffered log order."""

    shared = execution_root / "_shared"
    state: Mapping[str, Any] | None = None
    state_path = shared / "execution_state.json"
    try:
        candidate = read_json(state_path)
    except (OSError, TypeError, ValueError):
        candidate = None
    if (
        isinstance(candidate, Mapping)
        and candidate.get("executionId") == execution_id
        and candidate.get("status") in {"manual_required", "interrupted"}
    ):
        state = candidate
        stage = str(state.get("lastFailedStage") or "").strip()
        rendered = _render_typed_terminal_cause(
            stage=stage,
            message=state.get("nextAction"),
            issue_records=state.get("failedIssueRecords"),
        )
        state_records = state.get("failedIssueRecords")
        if rendered and any(
            isinstance(record, Mapping)
            for record in (state_records if isinstance(state_records, list) else [])
        ):
            return rendered
        state_fallback = rendered
    else:
        state_fallback = None

    command_root = shared / "command_packets"
    candidates: list[Path] = []
    failed_stage = str((state or {}).get("lastFailedStage") or "").strip()
    if failed_stage:
        candidates.append(command_root / f"{failed_stage}.json")
    try:
        candidates.extend(
            sorted(
                (
                    path
                    for path in command_root.glob("*.json")
                    if path not in candidates
                ),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
        )
    except OSError:
        pass
    for path in candidates:
        try:
            packet = read_json(path)
        except (OSError, TypeError, ValueError):
            continue
        if not isinstance(packet, Mapping) or packet.get("executionId") != execution_id:
            continue
        outputs = packet.get("outputs")
        if not isinstance(outputs, Mapping) or outputs.get("status") != "failed":
            continue
        stage = str(packet.get("stage") or path.stem).strip()
        rendered = _render_typed_terminal_cause(
            stage=stage,
            message=outputs.get("message"),
            issue_records=outputs.get("issueRecords"),
        )
        if rendered:
            return rendered
    return state_fallback


def _heartbeat_age_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    return max(
        0.0,
        (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds(),
    )


def lane_process_evidence(
    *,
    slice_count: int,
    elapsed_seconds: float,
    max_rss_bytes: int,
    heartbeat_at: str | None,
    owner: str | None = None,
    signal_name: str | None = None,
) -> dict[str, object]:
    evidence: dict[str, object] = {
        "sliceCount": slice_count,
        "resumeCount": slice_count - 1,
        "elapsedSeconds": elapsed_seconds,
        "maxRssBytes": max_rss_bytes,
    }
    if heartbeat_at is not None:
        evidence["lastExecutionHeartbeatAt"] = heartbeat_at
        evidence["heartbeatAgeSeconds"] = _heartbeat_age_seconds(heartbeat_at) or 0.0
    if owner is not None:
        evidence["terminationOwner"] = owner
    if signal_name is not None:
        evidence["terminationSignal"] = signal_name
    return evidence


def termination_owner(return_code: int) -> tuple[str, str | None]:
    """Classify ownership without claiming that every SIGKILL is OOM."""

    if return_code >= 0:
        return "lane_process", None
    try:
        signal_name = signal.Signals(-return_code).name
    except ValueError:
        signal_name = f"SIGNAL_{-return_code}"
    return "external_or_kernel", signal_name


__all__ = [
    "lane_process_evidence",
    "termination_owner",
    "typed_execution_terminal_cause",
]
