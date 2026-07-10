"""Baseline freeze packet and coverage-target helpers for workflow runs."""
from __future__ import annotations

from pathlib import Path

from _common.entity_extract import require_domain_etype
from _common.io import read_json
from _common.paths import task_baseline_freeze_packet_path

def _load_baseline_packet(task_id: str, packet_path: Path | None = None) -> tuple[Path, dict]:
    path = packet_path or task_baseline_freeze_packet_path(task_id)
    if not path.is_file():
        raise RuntimeError(
            f"missing baseline freeze packet: {path}. "
            f"Run `qwq-data data baseline --task {task_id}` first."
        )
    packet = read_json(path)
    if not isinstance(packet, dict):
        raise RuntimeError(f"baseline freeze packet unreadable: {path}")
    if str(packet.get("taskId") or "").strip() != task_id:
        raise RuntimeError(
            f"baseline freeze packet taskId mismatch: {packet.get('taskId')} != {task_id}"
        )
    if str(packet.get("command") or "").strip() != "data baseline":
        raise RuntimeError(f"baseline freeze packet command mismatch: {packet.get('command')}")
    return path, packet


# ─── coverage 实体解析（download/build 的输入）────────────────────────
def _coverage_entity_ids(spec: dict) -> list[str]:
    out: list[str] = []
    for target in (spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if name:
            out.append(name)
    return out


def _coverage_entity_type_map(spec: dict) -> dict[str, str]:
    """coverageTargets 中 canonical name / alias -> entityType。"""
    out: dict[str, str] = {}
    for target in (spec.get("scope") or {}).get("coverageTargets") or []:
        etype = str(target.get("entityType") or "").strip()
        if not etype:
            continue
        name = str(target.get("name") or "").strip()
        if name:
            out[name] = etype
        for alias in target.get("aliases") or []:
            alias_name = str(alias or "").strip()
            if alias_name:
                out[alias_name] = etype
    return out


def _coverage_entity_type_for_entity(spec: dict, entity_id: str) -> str:
    """单实体 entityType；优先 coverageTargets，回退 batch 级唯一类型。"""
    mapped = _coverage_entity_type_map(spec).get(str(entity_id or "").strip(), "")
    if mapped:
        require_domain_etype(mapped, context=f"scope.coverageTargets entityType for {entity_id}")
        return mapped
    return _coverage_entity_type(spec)


# ─── checkpoint 完成度探测（resume 判定 Agent 是否已物化产物）──────────
def _coverage_entity_type(spec: dict) -> str:
    """coverageTargets/entityTypes 的 batch 级类型；多类型分区返回空串，由 per-entity 解析。"""
    scope = spec.get("scope") or {}
    targets = scope.get("coverageTargets") or []
    target_types = {
        str(target.get("entityType") or "").strip()
        for target in targets
        if str(target.get("entityType") or "").strip()
    }
    if len(target_types) > 1:
        return ""
    if target_types:
        only = next(iter(target_types))
        require_domain_etype(only, context="scope.coverageTargets[].entityType")
        return only
    types = [str(item).strip() for item in (scope.get("entityTypes") or []) if str(item).strip()]
    if not types:
        return ""
    if len(types) > 1:
        return ""
    require_domain_etype(types[0], context="scope.entityTypes[0]")
    return types[0]
