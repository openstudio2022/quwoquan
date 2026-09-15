"""从 generated fromWire 派生 Alpha 演练默认 response wire。

产物仅供 Alpha 本地演练使用，不进入在线用户制品。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_ENUM_RE = re.compile(
    r"enum\s+(\w+)\s*\{(.*?)\n\}",
    re.DOTALL,
)
_ENUM_VALUE_RE = re.compile(r'([A-Za-z_][\w]*)\s*\(\s*"([^"]+)"\s*\)')
_FACTORY_RE = re.compile(
    r"factory\s+(\w+)\.fromWire\(",
)

_ISO = "2026-01-01T00:00:00.000Z"
_STRING = "rehearsal"
_INT = 1
_BOOL = False

_SKIP_OPTIONAL_PREFIXES = (
    "map[",
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _contracts_root(root: Path) -> Path:
    return (
        root
        / "quwoquan_app"
        / "packages"
        / "quwoquan_cloud_contracts"
        / "lib"
        / "src"
    )


def _iter_contract_files(root: Path) -> list[Path]:
    src = _contracts_root(root)
    return sorted(
        path
        for path in src.rglob("*.g.dart")
        if "operation_contracts.g.dart" in path.name
        or path.name.endswith("_operation_contracts.g.dart")
        or path.name.endswith("shared_operation_enums.g.dart")
    )


def parse_enums(text: str) -> dict[str, str]:
    first_wire: dict[str, str] = {}
    for match in _ENUM_RE.finditer(text):
        name = match.group(1)
        body = match.group(2)
        values = _ENUM_VALUE_RE.findall(body)
        if values:
            first_wire[name] = values[0][1]
    return first_wire


def _is_optional_expr(expr: str) -> bool:
    stripped = expr.strip()
    return (
        stripped.startswith("map[")
        and " == null" in stripped
        and "?" in stripped
    ) or stripped.startswith("map[") and " == null" in stripped


def _classify_expr(expr: str, enums: dict[str, str]) -> tuple[str, Any]:
    text = " ".join(expr.strip().split())
    if _is_optional_expr(text):
        return ("omit", None)
    nested = re.search(r"(\w+)\.fromWire\(\s*_requiredObject\(map\[", text)
    if nested:
        return ("nested", nested.group(1))
    enum_match = re.search(r"(\w+)\.fromWire\(\s*map\[", text)
    if enum_match and enum_match.group(1) in enums:
        return ("enum", enums[enum_match.group(1)])
    if "_requiredList(" in text or "List<" in text:
        return ("list", [])
    if "_requiredBool(" in text:
        return ("bool", _BOOL)
    if "_requiredPositiveInt(" in text or "_requiredInt(" in text:
        return ("int", _INT)
    if "_requiredTimestamp(" in text:
        return ("timestamp", _ISO)
    if "_requiredNonBlankString(" in text or "_requiredString(" in text:
        return ("string", _STRING)
    if "Uri.parse" in text or "Uri." in text:
        return ("string", "https://rehearsal.local/asset")
    return ("string", _STRING)


def _extract_matching_paren(text: str, open_index: int) -> str:
    depth = 0
    i = open_index
    while i < len(text):
        char = text[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : i]
        i += 1
    return ""


def parse_fromwire_classes(
    text: str, enums: dict[str, str]
) -> dict[str, dict[str, tuple[str, Any]]]:
    result: dict[str, dict[str, tuple[str, Any]]] = {}
    for match in _FACTORY_RE.finditer(text):
        name = match.group(1)
        factory_body_start = text.find("{", match.end())
        if factory_body_start < 0:
            continue
        return_token = f"return {name}("
        return_at = text.find(return_token, factory_body_start)
        if return_at < 0 or return_at > factory_body_start + 8000:
            continue
        ctor = _extract_matching_paren(text, return_at + len(return_token) - 1)
        fields: dict[str, tuple[str, Any]] = {}
        for field_match in re.finditer(
            r"(\w+):\s*((?:.|\n)*?)(?=,\n      \w+:|\s*$)",
            ctor.strip(),
        ):
            field = field_match.group(1)
            expr = field_match.group(2)
            fields[field] = _classify_expr(expr, enums)
        result[name] = fields
    return result


def build_wire(
    name: str,
    classes: dict[str, dict[str, tuple[str, Any]]],
    stack: set[str] | None = None,
) -> dict[str, Any]:
    stack = stack or set()
    if name in stack:
        return {}
    stack.add(name)
    fields = classes.get(name, {})
    wire: dict[str, Any] = {}
    for field, (kind, value) in fields.items():
        if kind == "omit":
            continue
        if kind == "nested":
            nested_name = str(value)
            wire[field] = build_wire(nested_name, classes, stack)
            continue
        wire[field] = value
    stack.remove(name)
    return wire


def dart_literal(value: Any, indent: int = 2) -> str:
    pad = " " * indent
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        if not value:
            return "const <Object>[]"
        items = ", ".join(dart_literal(item, indent + 2) for item in value)
        return f"const <Object>[{items}]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = ",\n".join(
            f'{pad}  "{key}": {dart_literal(item, indent + 2)}'
            for key, item in value.items()
        )
        return "{\n" + inner + f",\n{pad}}}"
    raise TypeError(f"unsupported literal {type(value)}")


def collect_response_entities(root: Path) -> tuple[str, ...]:
    graph = json.loads(
        (root / "quwoquan_service/generated/contract_graph.json").read_text(
            encoding="utf-8"
        )
    )
    names: list[str] = []
    seen: set[str] = set()
    for operation in graph.get("operations") or []:
        if not isinstance(operation, dict) or not operation.get("clientContract"):
            continue
        entity = str(operation.get("responseEntity") or "").strip()
        if entity and entity not in seen:
            seen.add(entity)
            names.append(entity)
    return tuple(names)


def generate(root: Path | None = None) -> str:
    repo = root or repository_root()
    enums: dict[str, str] = {}
    classes: dict[str, dict[str, tuple[str, Any]]] = {}
    for path in _iter_contract_files(repo):
        text = path.read_text(encoding="utf-8")
        enums.update(parse_enums(text))
        classes.update(parse_fromwire_classes(text, enums))
    entities = collect_response_entities(repo)
    wires: dict[str, dict[str, Any]] = {}
    for name in entities:
        wires[name] = build_wire(name, classes)
    lines = [
        "// Code generated by generate_alpha_rehearsal_wires.py. DO NOT EDIT.",
        "// Alpha-only default response templates derived from generated fromWire.",
        "",
        "const Map<String, Map<String, Object?>> kAlphaRehearsalDefaultResponseWires =",
        "    <String, Map<String, Object?>>{",
    ]
    for name in sorted(wires):
        literal = dart_literal(wires[name], indent=6)
        lines.append(f'      "{name}": <String, Object?>{literal},')
    lines.append("    };")
    lines.append("")
    return "\n".join(lines)


def output_path(root: Path | None = None) -> Path:
    repo = root or repository_root()
    return (
        repo
        / "quwoquan_app"
        / "lib"
        / "runtime"
        / "alpha_rehearsal"
        / "generated"
        / "default_response_wires.g.dart"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--root", default="")
    args = parser.parse_args()
    repo = Path(args.root) if args.root else repository_root()
    text = generate(repo)
    path = output_path(repo)
    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(path)
        return
    print(text)


if __name__ == "__main__":
    main()
