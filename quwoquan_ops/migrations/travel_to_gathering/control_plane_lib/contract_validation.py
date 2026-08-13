"""按 canonical fields contract 校验映射产物文档（逐字来自原 ``control_plane.py``）。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any


def _constraints(field: Mapping[str, Any]) -> set[str]:
    value = field.get("constraints")
    return {str(item) for item in value} if isinstance(value, list) else set()


def _validate_scalar_type(
    value: Any,
    type_name: str,
    *,
    location: str,
    enums: Mapping[str, Any],
    enum_ref: str,
) -> list[str]:
    if type_name in {"string", "json"}:
        if type_name == "string" and not isinstance(value, str):
            return [f"{location} must be string"]
        return []
    if type_name in {"int", "int64"}:
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"{location} must be integer"]
        return []
    if type_name == "bool":
        return [] if isinstance(value, bool) else [f"{location} must be bool"]
    if type_name == "timestamp":
        if not isinstance(value, str):
            return [f"{location} must be timestamp string"]
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return [f"{location} must be RFC3339 timestamp"]
        return []
    if type_name == "enum":
        definition = enums.get(enum_ref)
        allowed = definition.get("values") if isinstance(definition, dict) else None
        if not isinstance(allowed, list) or value not in allowed:
            return [f"{location} is not in {enum_ref}"]
        return []
    return []


def _validate_field_value(
    value: Any,
    field: Mapping[str, Any],
    *,
    location: str,
    types: Mapping[str, Any],
    enums: Mapping[str, Any],
) -> list[str]:
    constraints = _constraints(field)
    if value is None:
        return [] if "NULLABLE" in constraints else [f"{location} may not be null"]
    type_name = str(field.get("type") or "")
    if type_name.startswith("[]"):
        if not isinstance(value, list):
            return [f"{location} must be list"]
        errors: list[str] = []
        max_items = field.get("max_items")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{location} exceeds max_items")
        item_type = type_name[2:]
        item_field = {"type": item_type, "constraints": ["NOT_NULL"]}
        for index, item in enumerate(value):
            errors.extend(
                _validate_field_value(
                    item,
                    item_field,
                    location=f"{location}[{index}]",
                    types=types,
                    enums=enums,
                )
            )
        return errors
    if type_name == "object":
        type_name = str(field.get("object_ref") or "")
    if type_name in types:
        definition = types[type_name]
        if not isinstance(value, dict) or not isinstance(definition, dict):
            return [f"{location} must be {type_name} object"]
        nested_fields = definition.get("fields")
        if not isinstance(nested_fields, list):
            return [f"{location} has invalid contract definition"]
        expected = {
            str(item.get("name") or "")
            for item in nested_fields
            if isinstance(item, dict)
        }
        errors = []
        unknown = set(value) - expected
        if unknown:
            errors.append(f"{location} has unknown fields: {sorted(unknown)}")
        for nested in nested_fields:
            if not isinstance(nested, dict):
                continue
            name = str(nested.get("name") or "")
            if name not in value:
                if "NULLABLE" not in _constraints(nested):
                    errors.append(f"{location}.{name} is missing")
                continue
            errors.extend(
                _validate_field_value(
                    value[name],
                    nested,
                    location=f"{location}.{name}",
                    types=types,
                    enums=enums,
                )
            )
        return errors
    errors = _validate_scalar_type(
        value,
        type_name,
        location=location,
        enums=enums,
        enum_ref=str(field.get("enum_ref") or ""),
    )
    if "NOT_BLANK" in constraints and isinstance(value, str) and not value.strip():
        errors.append(f"{location} may not be blank")
    max_bytes = field.get("max_utf8_bytes")
    if (
        isinstance(max_bytes, int)
        and isinstance(value, str)
        and len(value.encode("utf-8")) > max_bytes
    ):
        errors.append(f"{location} exceeds max_utf8_bytes")
    return errors


def _validate_contract_document(
    document: Mapping[str, Any],
    fields_contract: Mapping[str, Any],
    *,
    object_name: str,
) -> list[str]:
    root_fields = fields_contract.get("fields")
    types = fields_contract.get("types")
    enums = fields_contract.get("enums")
    if (
        not isinstance(root_fields, list)
        or not isinstance(types, dict)
        or not isinstance(enums, dict)
    ):
        return [f"canonical {object_name} fields contract is incomplete"]
    expected = {
        str(field.get("name") or "") for field in root_fields if isinstance(field, dict)
    }
    errors: list[str] = []
    unknown = set(document) - expected
    if unknown:
        errors.append(f"{object_name} has unknown fields: {sorted(unknown)}")
    for field in root_fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        if name not in document:
            if "NULLABLE" not in _constraints(field):
                errors.append(f"{object_name}.{name} is missing")
            continue
        errors.extend(
            _validate_field_value(
                document[name],
                field,
                location=f"{object_name}.{name}",
                types=types,
                enums=enums,
            )
        )
    return errors


def validate_gathering_document(
    document: Mapping[str, Any],
    fields_contract: Mapping[str, Any],
) -> list[str]:
    return _validate_contract_document(
        document,
        fields_contract,
        object_name="Gathering",
    )
