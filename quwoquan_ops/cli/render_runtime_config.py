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
CROSS_SERVICE_DEFAULTS_FILENAME = "config-defaults.yaml"

# 未匹配到任何跨服务默认时的哨兵。None 是合法的 YAML 值，不能兼作「没有」。
MISSING = object()


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


# 跨服务默认的声明位：全局一层、每环境一层。两层都只给服务 schema 已声明的键
# 供值，不引入新键——键的真相源仍是各服务 config/schema.yaml。
def cross_service_defaults_paths(root: Path, environment: str) -> tuple[Path, Path]:
    base = root / "quwoquan_ops/environments"
    return (
        base / CROSS_SERVICE_DEFAULTS_FILENAME,
        base / environment / CROSS_SERVICE_DEFAULTS_FILENAME,
    )


def load_cross_service_defaults(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = load_yaml(path)
    defaults = payload.get("defaults", {}) or {}
    if not isinstance(defaults, dict):
        raise ValueError(f"{path}: defaults must be a mapping")
    for pattern in defaults:
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError(f"{path}: every default pattern must be a non-empty string")
    return defaults


def pattern_matches(pattern: str, rendered_key: str) -> bool:
    pattern_parts = pattern.split(".")
    key_parts = rendered_key.split(".")
    if len(pattern_parts) != len(key_parts):
        return False
    return all(
        expected == "*" or expected == actual
        for expected, actual in zip(pattern_parts, key_parts)
    )


# 同层内多个模式命中同一个键时取更具体的那个（通配段更少）。并列即声明歧义，
# 判否而不是挑一个——挑哪个都是代码替声明者做决定。
def resolve_layer_default(path: Path, defaults: dict[str, Any], rendered_key: str) -> Any:
    matches = [
        (pattern, value)
        for pattern, value in defaults.items()
        if pattern_matches(pattern, rendered_key)
    ]
    if not matches:
        return MISSING
    best_specificity = min(pattern.count("*") for pattern, _ in matches)
    finalists = [
        (pattern, value)
        for pattern, value in matches
        if pattern.count("*") == best_specificity
    ]
    if len(finalists) > 1:
        patterns = sorted(pattern for pattern, _ in finalists)
        raise ValueError(
            f"{path}: ambiguous defaults for {rendered_key}: {patterns}; "
            "make one pattern more specific"
        )
    return finalists[0][1]


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

    global_defaults_path, environment_defaults_path = cross_service_defaults_paths(
        root, environment
    )
    if not global_defaults_path.is_file():
        raise ValueError(
            f"missing required global cross-service defaults: {global_defaults_path}"
        )
    layered_defaults = (
        (environment_defaults_path, load_cross_service_defaults(environment_defaults_path)),
        (global_defaults_path, load_cross_service_defaults(global_defaults_path)),
    )

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
        # 取值优先级：服务环境自定义 > 环境跨服务默认 > 全局跨服务默认 > 服务 schema
        # default。每一层都是显式声明，生效值必然能指回一处写下它的文件。
        source_path = environment_path
        value = MISSING
        if key in overrides:
            value = overrides[key]
        else:
            for defaults_path, defaults in layered_defaults:
                candidate = resolve_layer_default(
                    defaults_path, defaults, rendered_path(workload, key)
                )
                if candidate is not MISSING:
                    if entry.get("sensitive"):
                        raise ValueError(
                            f"{defaults_path}: sensitive key must use secretRef, "
                            f"cross-service defaults cannot supply it: {key}"
                        )
                    source_path = defaults_path
                    value = candidate
                    break
        if value is MISSING:
            if "default" not in entry:
                continue
            source_path = schema_path
            value = entry["default"]
        validate_scalar_type(source_path, key, entry, value)
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
