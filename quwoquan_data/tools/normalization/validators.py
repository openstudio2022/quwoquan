from __future__ import annotations

from pathlib import Path
from typing import Any

from common import read_json
from normalization.io_contracts import input_schema_path, output_schema_path, schema_path


class NormalizationValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def _path_str(path: list[str]) -> str:
    return ".".join(path) if path else "<root>"


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _validate_one_of(value: Any, candidates: list[dict[str, Any]], path: list[str]) -> list[str]:
    collected: list[list[str]] = []
    for candidate in candidates:
        errors: list[str] = []
        _validate_value(value, candidate, path, errors)
        if not errors:
            return []
        collected.append(errors)
    if not collected:
        return [f"{_path_str(path)}: oneOf 为空"]
    sample = collected[0][:3]
    return [f"{_path_str(path)}: 不匹配任何 oneOf 备选"] + sample


def _validate_value(value: Any, schema: dict[str, Any], path: list[str], errors: list[str]) -> None:
    if "oneOf" in schema:
        errors.extend(_validate_one_of(value, [dict(item) for item in schema.get("oneOf") or []], path))
        return

    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(_matches_type(value, item) for item in expected_type):
            errors.append(f"{_path_str(path)}: 类型不匹配，期望 {expected_type}，实际 {type(value).__name__}")
            return
    elif isinstance(expected_type, str):
        if not _matches_type(value, expected_type):
            errors.append(f"{_path_str(path)}: 类型不匹配，期望 {expected_type}，实际 {type(value).__name__}")
            return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{_path_str(path)}: 值 {value!r} 不在 enum 中")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"{_path_str(path)}: 长度 {len(value)} < minLength {min_length}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{_path_str(path)}: 数值 {value} < minimum {minimum}")

    if isinstance(value, list):
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for index, item in enumerate(value):
                _validate_value(item, items_schema, path + [f"[{index}]"], errors)

    if isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append(f"{_path_str(path)}: 缺少必填字段 {key}")
        properties = schema.get("properties") or {}
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties and isinstance(properties[key], dict):
                _validate_value(item, dict(properties[key]), path + [key], errors)
                continue
            if additional is False:
                errors.append(f"{_path_str(path)}: 不允许额外字段 {key}")
                continue
            if isinstance(additional, dict):
                _validate_value(item, dict(additional), path + [key], errors)


def load_schema(schema_filename: str) -> dict[str, Any]:
    payload = read_json(schema_path(schema_filename))
    if not isinstance(payload, dict):
        raise NormalizationValidationError([f"schema 非法（非 object）: {schema_filename}"])
    return payload


def validate_payload_against_schema(payload: Any, schema_filename: str) -> None:
    schema = load_schema(schema_filename)
    errors: list[str] = []
    _validate_value(payload, schema, [], errors)
    if errors:
        raise NormalizationValidationError(errors)


def validate_input_payload(stage: str, payload: Any) -> None:
    validate_payload_against_schema(payload, input_schema_path(stage).name)


def validate_output_payload(stage: str, payload: Any) -> None:
    validate_payload_against_schema(payload, output_schema_path(stage).name)


def validate_json_file(path: Path, schema_filename: str) -> dict[str, Any]:
    payload = read_json(path)
    validate_payload_against_schema(payload, schema_filename)
    return payload


def validate_input_file(stage: str, path: Path) -> dict[str, Any]:
    payload = read_json(path)
    validate_input_payload(stage, payload)
    return payload


def validate_output_file(stage: str, path: Path) -> dict[str, Any]:
    payload = read_json(path)
    validate_output_payload(stage, payload)
    return payload

