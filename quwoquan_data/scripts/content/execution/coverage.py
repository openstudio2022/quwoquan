"""Execution-spec coverage targets 的强边界解析。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from governance.coverage.entity_extract import require_domain_etype


@dataclass(frozen=True)
class CoverageTarget:
    name: str
    entity_type: str
    aliases: tuple[str, ...]


def coverage_targets(spec: Mapping[str, Any]) -> tuple[CoverageTarget, ...]:
    """Decode the frozen targets from the validated execution boundary."""
    scope = spec.get("scope")
    if not isinstance(scope, Mapping):
        return ()
    rows = scope.get("coverageTargets") or []
    targets: list[CoverageTarget] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "").strip()
        entity_type = str(row.get("entityType") or "").strip()
        if not name or not entity_type:
            continue
        require_domain_etype(entity_type, context=f"scope target entityType for {name}")
        aliases = tuple(
            alias
            for value in (row.get("aliases") or [])
            if (alias := str(value or "").strip())
        )
        targets.append(CoverageTarget(name=name, entity_type=entity_type, aliases=aliases))
    return tuple(targets)


def coverage_entity_ids(spec: Mapping[str, Any]) -> list[str]:
    """Return primary coverage target names in declaration order."""
    scope = spec.get("scope")
    if not isinstance(scope, Mapping):
        return []
    entity_ids: list[str] = []
    for row in scope.get("coverageTargets") or []:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            entity_ids.append(name)
    return entity_ids


def coverage_entity_type_for_entity(spec: Mapping[str, Any], entity_id: str) -> str:
    """Resolve a frozen target or alias to its declared domain type."""
    normalized = str(entity_id or "").strip()
    for target in coverage_targets(spec):
        if normalized == target.name or normalized in target.aliases:
            return target.entity_type
    return coverage_entity_type(spec)


def coverage_entity_type(spec: Mapping[str, Any]) -> str:
    """Return the batch type only for a homogeneous target set."""
    primary_ids = set(coverage_entity_ids(spec))
    types = {
        target.entity_type
        for target in coverage_targets(spec)
        if target.name in primary_ids
    }
    if len(types) == 1:
        return next(iter(types))
    if types:
        return ""
    scope = spec.get("scope")
    if not isinstance(scope, Mapping):
        return ""
    declared = [str(value).strip() for value in (scope.get("entityTypes") or []) if str(value).strip()]
    if len(declared) != 1:
        return ""
    require_domain_etype(declared[0], context="scope.entityTypes[0]")
    return declared[0]
