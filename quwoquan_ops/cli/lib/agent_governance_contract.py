"""Agent context 与 Review plan 的受版本控制 schema 契约读取器。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONTRACT_PATH = (
    Path(__file__).resolve().parents[3]
    / "quwoquan_ops/policies/agent_governance_contract.yaml"
)


@lru_cache(maxsize=1)
def load_agent_governance_contract() -> dict[str, Any]:
    value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("agent governance contract schema_version 必须为 1")
    for section in ("feature_context_manifest", "review_plan"):
        definition = value.get(section)
        if not isinstance(definition, dict):
            raise TypeError(f"agent governance contract 缺映射段 {section}")
        version = definition.get("schema_version")
        if not isinstance(version, int) or version <= 0:
            raise ValueError(
                f"agent governance contract {section}.schema_version 必须为正整数"
            )
    return value


def contract_section(name: str) -> dict[str, Any]:
    value = load_agent_governance_contract().get(name)
    if not isinstance(value, dict):
        raise TypeError(f"agent governance contract 缺映射段 {name}")
    return value


def contract_schema_version(section: str) -> int:
    version = contract_section(section).get("schema_version")
    if not isinstance(version, int) or version <= 0:
        raise ValueError(
            f"agent governance contract {section}.schema_version 必须为正整数"
        )
    return version


def declared_fields(section: str, declaration: str) -> tuple[str, ...]:
    definition = contract_section(section)
    fields = definition.get(declaration)
    if (
        not isinstance(fields, list)
        or not fields
        or not all(isinstance(item, str) and item for item in fields)
        or len(fields) != len(set(fields))
    ):
        raise ValueError(f"agent governance contract {section}.{declaration} 非法")
    return tuple(fields)


def validate_declared_fields(
    payload: dict[str, Any],
    section: str,
    declaration: str,
) -> None:
    expected = declared_fields(section, declaration)
    missing = [field for field in expected if field not in payload]
    extra = sorted(set(payload) - set(expected))
    if missing or extra:
        raise ValueError(
            f"{section}.{declaration} 字段漂移："
            f"missing={missing or []}, extra={extra or []}"
        )


def declared_object(
    payload: dict[str, Any],
    section: str,
    declaration: str,
) -> dict[str, Any]:
    validate_declared_fields(payload, section, declaration)
    return {field: payload[field] for field in declared_fields(section, declaration)}


def validate_required_fields(payload: dict[str, Any], section: str) -> None:
    validate_declared_fields(payload, section, "required_fields")


def validate_schema_version(payload: dict[str, Any], section: str) -> None:
    expected = contract_schema_version(section)
    actual = payload.get("schema_version")
    if actual != expected:
        raise ValueError(
            f"{section}.schema_version 必须为 {expected}，实际为 {actual!r}"
        )


def validate_feature_context_manifest(payload: dict[str, Any]) -> None:
    """Validate one manifest at the producer and every consumer boundary."""

    validate_schema_version(payload, "feature_context_manifest")
    validate_required_fields(payload, "feature_context_manifest")
    for field, declaration in (
        ("owner_chain", "owner_chain_fields"),
        ("canonical_contexts", "context_fields"),
        ("open_items", "open_item_fields"),
    ):
        values = payload[field]
        if not isinstance(values, list):
            raise TypeError(f"feature_context_manifest.{field} 必须为列表")
        for value in values:
            if not isinstance(value, dict):
                raise TypeError(f"feature_context_manifest.{field} 项必须为映射")
            validate_declared_fields(
                value,
                "feature_context_manifest",
                declaration,
            )
    for field in ("applicable_agents", "profiles"):
        values = payload[field]
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            raise TypeError(f"feature_context_manifest.{field} 必须为非空字符串列表")
    for field in ("target", "resolved_owner"):
        if not isinstance(payload[field], str) or not payload[field]:
            raise TypeError(f"feature_context_manifest.{field} 必须为非空字符串")
