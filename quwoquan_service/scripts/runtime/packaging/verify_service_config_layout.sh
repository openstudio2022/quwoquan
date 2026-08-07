#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../" && pwd)"
cd "$ROOT"

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
import re
import yaml

root = Path.cwd()
service_roots = sorted(
    path.parent.parent
    for path in (root / "quwoquan_service/services").glob("*/contracts/domain.yaml")
)
if not service_roots:
    raise SystemExit("no self-describing domain services found")
control_plane = root / "quwoquan_service/control-plane/platform-ops"
all_roots = service_roots + ([control_plane] if control_plane.is_dir() else [])

global_config_sources = [
    root / "quwoquan_service/contracts/metadata/platform/config.yaml",
    root / "quwoquan_service/contracts/metadata/_control_plane/product/config.yaml",
    root / "quwoquan_ops/environments/config",
]
remaining = [str(path) for path in global_config_sources if path.exists()]
if remaining:
    raise SystemExit("global service config truth sources are forbidden: " + ", ".join(remaining))

all_keys: dict[str, Path] = {}
for owner in all_roots:
    schema_path = owner / "config/schema.yaml"
    if not schema_path.is_file():
        raise SystemExit(f"missing config schema: {schema_path}")
    schema = yaml.safe_load(schema_path.read_text()) or {}
    entries = schema.get("configs", []) or []
    if not isinstance(entries, list):
        raise SystemExit(f"{schema_path}: configs must be a list")
    definitions = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
            raise SystemExit(f"{schema_path}: invalid config definition")
        key = entry["key"]
        if key in definitions:
            raise SystemExit(f"{schema_path}: duplicate key {key}")
        if key in all_keys:
            raise SystemExit(f"config key has two owners: {key}: {all_keys[key]} and {schema_path}")
        definitions[key] = entry
        all_keys[key] = schema_path

    environments_root = owner / "environments"
    envs = sorted(path.name for path in environments_root.iterdir() if path.is_dir())
    if envs != ["alpha", "beta", "gamma", "prod"]:
        raise SystemExit(f"{owner}: environment set must be alpha/beta/gamma/prod, got {envs}")
    for env in envs:
        path = environments_root / env / "config.yaml"
        if not path.is_file():
            raise SystemExit(f"missing environment config: {path}")
        payload = yaml.safe_load(path.read_text()) or {}
        allowed_sections = {"overrides", "secretRefs", "externalBindings"}
        unknown_sections = set(payload) - allowed_sections
        if unknown_sections:
            raise SystemExit(f"{path}: unknown sections {sorted(unknown_sections)}")
        overrides = payload.get("overrides", {}) or {}
        refs = payload.get("secretRefs", {}) or {}
        bindings = payload.get("externalBindings", {}) or {}
        if not all(isinstance(item, dict) for item in (overrides, refs, bindings)):
            raise SystemExit(f"{path}: overrides, secretRefs and externalBindings must be mappings")
        if set(overrides) & set(refs):
            raise SystemExit(f"{path}: key cannot be both override and secretRef")
        for key in set(overrides) | set(refs):
            if key not in definitions:
                raise SystemExit(f"{path}: undefined or foreign config key {key}")
        for key, ref in refs.items():
            if not definitions[key].get("sensitive"):
                raise SystemExit(f"{path}: non-sensitive key uses secretRef: {key}")
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", str(ref)):
                raise SystemExit(f"{path}: invalid secret reference for {key}: {ref}")
        for key in overrides:
            if definitions[key].get("sensitive"):
                raise SystemExit(f"{path}: sensitive key must use secretRef: {key}")
            if "default" in definitions[key] and overrides[key] == definitions[key]["default"]:
                raise SystemExit(f"{path}: override duplicates schema default for {key}")
        text = path.read_text()
        for other_env in {"alpha", "beta", "gamma", "prod"} - {env}:
            if re.search(rf"environments[/\\]{other_env}(?:[/\\]|$)", text):
                raise SystemExit(f"{path}: environment inheritance/reference to {other_env} is forbidden")

print(f"[verify] OK: {len(all_keys)} unique definitions, {len(service_roots)} self-describing services + platform-ops, four autonomous environments")
PY
