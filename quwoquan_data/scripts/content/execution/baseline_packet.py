"""Baseline packet 的唯一读取边界。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.io import read_json
from content.execution.workspace import execution_baseline_freeze_packet_path


def load_baseline_packet(execution_id: str, packet_path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    path = packet_path or execution_baseline_freeze_packet_path(execution_id)
    if not path.is_file():
        raise RuntimeError(
            f"missing baseline freeze packet: {path}. "
            f"Run `qwq-data task geo-homepages --execution-id {execution_id} ...` first."
        )
    packet = read_json(path)
    if not isinstance(packet, dict):
        raise RuntimeError(f"baseline freeze packet unreadable: {path}")
    if str(packet.get("executionId") or "").strip() != execution_id:
        raise RuntimeError(
            f"baseline freeze packet executionId mismatch: {packet.get('executionId')} != {execution_id}"
        )
    if str(packet.get("command") or "").strip() != "content execution baseline":
        raise RuntimeError(f"baseline freeze packet command mismatch: {packet.get('command')}")
    return path, packet
