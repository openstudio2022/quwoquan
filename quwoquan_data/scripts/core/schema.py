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
    return _load_schema_path(schema_path, stack=())


def _load_schema_path(schema_path: Path, *, stack: tuple[Path, ...]) -> dict:
    resolved_path = schema_path.resolve()
    schema_root = SCHEMA_ROOT.resolve()
    try:
        resolved_path.relative_to(schema_root)
    except ValueError as exc:
        raise ValueError(f"Schema ref escapes schema root: {schema_path}") from exc
    if resolved_path in stack:
        chain = " -> ".join(str(path) for path in (*stack, resolved_path))
        raise ValueError(f"Schema ref cycle: {chain}")
    with resolved_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Schema must be an object: {resolved_path}")
    return _resolve_external_refs(payload, current_path=resolved_path, stack=(*stack, resolved_path))


def _resolve_external_refs(value: Any, *, current_path: Path, stack: tuple[Path, ...]) -> Any:
    """Inline same-schema-root external refs before strict local validation.

    The data contracts intentionally split reusable definitions such as
    ``gate_verdict.schema.json`` into their own files. The lightweight runtime
    validator remains fail-closed, but must resolve those local contract refs
    rather than treating a valid schema as unsupported.
    """
    if isinstance(value, list):
        return [
            _resolve_external_refs(item, current_path=current_path, stack=stack)
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    ref = value.get("$ref")
    if isinstance(ref, str) and not ref.startswith("#/"):
        file_ref, separator, pointer = ref.partition("#")
        if not file_ref:
            raise ValueError(f"Unsupported schema ref: {ref!r}")
        referenced = _load_schema_path(current_path.parent / file_ref, stack=stack)
        target: Any = referenced
        if separator and pointer:
            for raw_part in pointer.lstrip("/").split("/"):
                try:
                    target = target[raw_part.replace("~1", "/").replace("~0", "~")]
                except (KeyError, TypeError) as exc:
                    raise ValueError(f"Cannot resolve schema ref {ref!r} from {current_path}") from exc
        if not isinstance(target, dict):
            raise ValueError(f"Schema ref does not point to an object: {ref!r}")
        siblings = {key: item for key, item in value.items() if key != "$ref"}
        merged = {**target, **siblings}
        return _resolve_external_refs(merged, current_path=current_path, stack=stack)
    return {
        key: _resolve_external_refs(item, current_path=current_path, stack=stack)
        for key, item in value.items()
    }


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


def assert_valid(instance: Any, command: str, schema_name: str, *, label: str = "") -> None:
    """中间件写盘前统一 Schema 门（batch/workflow/command/lease/ship/import）。

    校验失败即 raise，禁止把不合契约的中间件文档落盘（fail-closed）。
    """
    schema = load_schema(command, schema_name)
    issues = validate_strict(instance, schema)
    if issues:
        head = f"[{label or schema_name}] schema violation:"
        raise ValueError(head + "\n  - " + "\n  - ".join(issues[:20]))


def validate_strict(
    instance: Any,
    schema: dict,
    *,
    path: str = "$",
    _root_schema: dict | None = None,
) -> list[str]:
    """递归严格校验（无 jsonschema 依赖；recipe/manifest 等契约文档用）。

    支持 type / required / properties / additionalProperties(false|schema) /
    enum / const / minimum / maximum / minLength / pattern / items /
    patternProperties(简化: 不支持)。
    未知字段在 additionalProperties=false 时必须失败（fail-closed）。
    """
    errors: list[str] = []
    root_schema = _root_schema or schema
    ref = schema.get("$ref")
    if isinstance(ref, str):
        if not ref.startswith("#/"):
            return [f"{path}: 不支持外部 $ref {ref!r}"]
        target: Any = root_schema
        try:
            for raw_part in ref[2:].split("/"):
                part = raw_part.replace("~1", "/").replace("~0", "~")
                target = target[part]
        except (KeyError, TypeError):
            return [f"{path}: 无法解析 $ref {ref!r}"]
        if not isinstance(target, dict):
            return [f"{path}: $ref {ref!r} 未指向 schema 对象"]
        return validate_strict(
            instance,
            target,
            path=path,
            _root_schema=root_schema,
        )
    expected_type = schema.get("type")
    if expected_type is not None and not _type_matches(instance, expected_type):
        errors.append(f"{path}: 期望 {expected_type}，实得 {type(instance).__name__}")
        return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: 必须等于 {schema['const']!r}，实得 {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} 不在枚举 {schema['enum']}")
    if isinstance(instance, str):
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < int(min_length):
            errors.append(f"{path}: 长度 {len(instance)} < minLength {min_length}")
        pattern = schema.get("pattern")
        if pattern is not None:
            import re as _re

            if _re.search(str(pattern), instance) is None:
                errors.append(f"{path}: {instance!r} 不匹配 pattern {pattern!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} > maximum {schema['maximum']}")
    if isinstance(instance, dict):
        properties = schema.get("properties") or {}
        for field in schema.get("required", []):
            if field not in instance:
                errors.append(f"{path}: 缺 required 字段 {field!r}")
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in properties:
                errors.extend(
                    validate_strict(
                        value,
                        properties[key],
                        path=f"{path}.{key}",
                        _root_schema=root_schema,
                    )
                )
            elif additional is False:
                errors.append(f"{path}: 未知字段 {key!r}（schema 未声明，fail-closed）")
            elif isinstance(additional, dict):
                errors.extend(
                    validate_strict(
                        value,
                        additional,
                        path=f"{path}.{key}",
                        _root_schema=root_schema,
                    )
                )
    if isinstance(instance, list) and isinstance(schema.get("items"), dict):
        for idx, item in enumerate(instance):
            errors.extend(
                validate_strict(
                    item,
                    schema["items"],
                    path=f"{path}[{idx}]",
                    _root_schema=root_schema,
                )
            )
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
