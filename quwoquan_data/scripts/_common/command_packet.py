"""标准命令 packet 生成/落盘 helper。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.io import write_json

PACKET_SCHEMA = "quwoquan.data.packet"


def build_packet(
    *,
    task_id: str,
    command: str,
    object_kind: str,
    object_ref: str,
    stage: str,
    read_policy: Sequence[str],
    stop_if: Sequence[str],
    output_policy: Sequence[str],
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any],
    handoff_to: str,
    evidence: Mapping[str, Any],
    summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "schemaVersion": PACKET_SCHEMA,
        "taskId": task_id,
        "command": command,
        "objectKind": object_kind,
        "objectRef": object_ref,
        "stage": stage,
        "readPolicy": list(read_policy),
        "stopIf": list(stop_if),
        "outputPolicy": list(output_policy),
        "inputs": dict(inputs),
        "outputs": dict(outputs),
        "handoffTo": handoff_to,
        "evidence": dict(evidence),
    }
    if summary is not None:
        packet["summary"] = dict(summary)
    return packet


def write_packet(path: Path, packet: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, dict(packet))
    return path
