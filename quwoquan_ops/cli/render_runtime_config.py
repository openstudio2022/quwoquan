#!/usr/bin/env python3
"""从服务自治配置定义渲染一个环境的只读运行配置。"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys
from typing import Any

sys.dont_write_bytecode = True

import yaml


ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
SECRET_REF_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping")
    return payload


def service_root(root: Path, workload: str) -> Path:
    if workload == "platform-ops-service":
        candidate = root / "quwoquan_service/control-plane/platform-ops"
    else:
        candidate = root / "quwoquan_service/services" / workload
    if not candidate.is_dir():
        raise ValueError(f"unknown service workload: {workload}")
    return candidate


def set_nested(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    cursor = target
    for part in parts[:-1]:
        child = cursor.setdefault(part, {})
        if not isinstance(child, dict):
            raise ValueError(f"config path collision at {dotted_path}")
        cursor = child
    cursor[parts[-1]] = value


def rendered_path(workload: str, key: str) -> str:
    prefix = f"sys.{workload}."
    if key.startswith(prefix):
        return key.removeprefix(prefix)
    return key


def validate_scalar_type(path: Path, key: str, definition: dict[str, Any], value: Any) -> None:
    declared = str(definition.get("type") or "").strip().lower()
    accepted: dict[str, tuple[type, ...]] = {
        "bool": (bool,),
        "boolean": (bool,),
        "int": (int,),
        "integer": (int,),
        "float": (int, float),
        "number": (int, float),
        "string": (str,),
        "list": (list,),
        "array": (list,),
        "map": (dict,),
        "object": (dict,),
    }
    expected = accepted.get(declared)
    if expected is None:
        raise ValueError(f"{path}: {key} has unsupported type {declared!r}")
    if isinstance(value, bool) and declared in {"int", "integer", "float", "number"}:
        raise ValueError(f"{path}: {key} must be {declared}, got bool")
    if not isinstance(value, expected):
        raise ValueError(f"{path}: {key} must be {declared}, got {type(value).__name__}")


def canonical_dump(payload: dict[str, Any]) -> bytes:
    return yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=True,
        width=120,
    ).encode("utf-8")


def render_workload(root: Path, environment: str, workload: str, output_path: Path) -> Path:
    owner = service_root(root, workload)
    schema_path = owner / "config/schema.yaml"
    environment_path = owner / f"environments/{environment}/config.yaml"
    if not schema_path.is_file():
        raise ValueError(f"missing service config schema: {schema_path}")
    if not environment_path.is_file():
        raise ValueError(f"missing service environment config: {environment_path}")

    schema = load_yaml(schema_path)
    environment_config = load_yaml(environment_path)
    raw_definitions = schema.get("configs", []) or []
    if not isinstance(raw_definitions, list):
        raise ValueError(f"{schema_path}: configs must be a list")
    definitions: dict[str, dict[str, Any]] = {}
    for entry in raw_definitions:
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
            raise ValueError(f"{schema_path}: every config definition must have a key")
        key = entry["key"]
        if key in definitions:
            raise ValueError(f"{schema_path}: duplicate config key {key}")
        definitions[key] = entry

    overrides = environment_config.get("overrides", {}) or {}
    secret_refs = environment_config.get("secretRefs", {}) or {}
    external_bindings = environment_config.get("externalBindings", {}) or {}
    for name, value in (
        ("overrides", overrides),
        ("secretRefs", secret_refs),
        ("externalBindings", external_bindings),
    ):
        if not isinstance(value, dict):
            raise ValueError(f"{environment_path}: {name} must be a mapping")

    configured = set(overrides) | set(secret_refs)
    unknown = configured - set(definitions)
    if unknown:
        raise ValueError(f"{environment_path}: unknown config keys: {sorted(unknown)}")
    overlap = set(overrides) & set(secret_refs)
    if overlap:
        raise ValueError(f"{environment_path}: keys cannot be override and secretRef: {sorted(overlap)}")

    rendered: dict[str, Any] = {}
    for key, entry in sorted(definitions.items()):
        if key in secret_refs:
            reference = str(secret_refs[key]).strip()
            if not entry.get("sensitive"):
                raise ValueError(f"{environment_path}: non-sensitive key uses secretRef: {key}")
            if not SECRET_REF_PATTERN.fullmatch(reference):
                raise ValueError(f"{environment_path}: invalid secretRef for {key}: {reference}")
            continue
        if entry.get("sensitive") and key in overrides:
            raise ValueError(f"{environment_path}: sensitive key must use secretRef: {key}")
        if key in overrides:
            value = overrides[key]
        elif "default" in entry:
            value = entry["default"]
        else:
            continue
        validate_scalar_type(environment_path, key, entry, value)
        # CONFIG_VERSION 是最终有效配置摘要，旧的手工 version 定义不参与渲染。
        if rendered_path(workload, key) == "config.version":
            continue
        set_nested(rendered, rendered_path(workload, key), value)

    if external_bindings:
        rendered["externalBindings"] = external_bindings
    digest = hashlib.sha256(canonical_dump(rendered)).hexdigest()
    set_nested(rendered, "config.version", f"sha256:{digest}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(rendered, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=ENVIRONMENTS)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = repository_root() / output_path
    print(render_workload(repository_root(), args.env, args.workload, output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
