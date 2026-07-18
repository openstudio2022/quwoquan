"""Execution-spec coverage targets 的强边界解析。"""
from __future__ import annotations

from typing import Any, Mapping

from content.execution.spec_contract import CoverageTarget, ExecutionSpec
from governance.coverage.entity_extract import require_domain_etype


def _scope(spec: ExecutionSpec | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(spec, ExecutionSpec):
        return spec.scope.to_dict()
    scope = spec.get("scope")
    return scope if isinstance(scope, Mapping) else {}


def coverage_targets(spec: ExecutionSpec | Mapping[str, Any]) -> tuple[CoverageTarget, ...]:
    """Decode the frozen targets from the validated execution boundary."""
    if isinstance(spec, ExecutionSpec):
        return spec.scope.coverage_targets
    scope = _scope(spec)
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


def coverage_entity_ids(spec: ExecutionSpec | Mapping[str, Any]) -> list[str]:
    """Return primary coverage target names in declaration order."""
    if isinstance(spec, ExecutionSpec):
        return [target.name for target in spec.scope.coverage_targets]
    scope = _scope(spec)
    entity_ids: list[str] = []
    for row in scope.get("coverageTargets") or []:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            entity_ids.append(name)
    return entity_ids


def coverage_entity_type_for_entity(
    spec: ExecutionSpec | Mapping[str, Any], entity_id: str
) -> str:
    """Resolve a frozen target or alias to its declared domain type."""
    normalized = str(entity_id or "").strip()
    for target in coverage_targets(spec):
        if normalized == target.name or normalized in target.aliases:
            return target.entity_type
    return coverage_entity_type(spec)


def coverage_entity_type(spec: ExecutionSpec | Mapping[str, Any]) -> str:
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
    declared = (
        list(spec.scope.entity_types)
        if isinstance(spec, ExecutionSpec)
        else [
            str(value).strip()
            for value in (_scope(spec).get("entityTypes") or [])
            if str(value).strip()
        ]
    )
    if len(declared) != 1:
        return ""
    require_domain_etype(declared[0], context="scope.entityTypes[0]")
    return declared[0]
