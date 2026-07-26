"""跨 Python/Go/Dart 可复现的 FilterCatalog JSON 编码。"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
import json
import math


def load_json_decimal(text: str) -> object:
    """按十进制词法读取 JSON，避免二进制浮点影响摘要。"""
    return json.loads(
        text,
        parse_float=Decimal,
        parse_int=Decimal,
    )


def canonical_json_bytes(value: object) -> bytes:
    return _canonical_json(value).encode("utf-8")


def pretty_json_text(value: object) -> str:
    return _pretty_json(value, depth=0) + "\n"


def _canonical_number(value: object) -> str:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float, Decimal),
    ):
        raise ValueError("canonical number 必须为 JSON number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical number 必须有限")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("canonical number 不是合法十进制数") from exc
    if not number.is_finite():
        raise ValueError("canonical number 必须有限")
    if number.is_zero():
        return "0"
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _canonical_json(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _canonical_number(value)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("canonical JSON object key 必须为 string")
        return "{" + ",".join(
            f"{_canonical_json(key)}:{_canonical_json(value[key])}"
            for key in sorted(value)
        ) + "}"
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return "[" + ",".join(_canonical_json(item) for item in value) + "]"
    raise ValueError(
        f"canonical JSON 不支持类型：{type(value).__name__}"
    )


def _pretty_json(value: object, *, depth: int) -> str:
    indent = "  " * depth
    child_indent = "  " * (depth + 1)
    if isinstance(value, Mapping):
        if not value:
            return "{}"
        rows = [
            (
                f"{child_indent}{json.dumps(key, ensure_ascii=False)}: "
                f"{_pretty_json(item, depth=depth + 1)}"
            )
            for key, item in value.items()
        ]
        return "{\n" + ",\n".join(rows) + f"\n{indent}}}"
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        if not value:
            return "[]"
        rows = [
            f"{child_indent}{_pretty_json(item, depth=depth + 1)}"
            for item in value
        ]
        return "[\n" + ",\n".join(rows) + f"\n{indent}]"
    return _canonical_json(value)
