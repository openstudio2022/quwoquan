"""JSON Schema validation utilities."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import SCHEMA_ROOT


def load_schema(command: str, schema_name: str) -> dict:
    """Load a schema file from schema/{command}/{schema_name}.schema.json."""
    schema_path = SCHEMA_ROOT / command / f"{schema_name}.schema.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


def validate_result(result: dict, command: str, schema_name: str) -> list[str]:
    """Validate a result dict against a schema. Returns list of error messages (empty = valid).

    Uses a lightweight check without jsonschema dependency:
    - required fields present
    - field types match (string, number, boolean, array, object)
    """
    schema = load_schema(command, schema_name)
    errors: list[str] = []

    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for field in required:
        if field not in result:
            errors.append(f"Missing required field: {field}")

    for field, value in result.items():
        if field in properties:
            expected_type = properties[field].get("type")
            if not _type_matches(value, expected_type):
                errors.append(f"Field '{field}' expected type '{expected_type}', got {type(value).__name__}")

    return errors


def _type_matches(value: Any, json_type: Any) -> bool:
    if json_type is None:
        return True
    # 支持 union 类型，如 ["string", "null"]
    if isinstance(json_type, (list, tuple)):
        return any(_type_matches(value, t) for t in json_type)
    if json_type == "null":
        return value is None
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    expected = type_map.get(json_type)
    if expected is None:
        return True
    # bool 是 int 子类，但 JSON integer/number 不应接受 bool
    if json_type in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, expected)
