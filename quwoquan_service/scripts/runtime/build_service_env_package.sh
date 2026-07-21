#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

service=""
env_name=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      service="${2:-}"
      shift 2
      ;;
    --env)
      env_name="${2:-}"
      shift 2
      ;;
    *)
      echo "FAIL: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done
service="${service:-${SERVICE:-}}"
env_name="${env_name:-${ENV:-}}"

case "$env_name" in
  alpha|beta|gamma|prod) ;;
  *)
    echo "FAIL: --env must be one of alpha|beta|gamma|prod" >&2
    exit 2
    ;;
esac
if [[ -z "$service" ]]; then
  echo "FAIL: --service is required" >&2
  exit 2
fi

cfg_root="quwoquan_service/services/${service}/configs"
default_cfg="${cfg_root}/default/config.yaml"
env_cfg="${cfg_root}/${env_name}/config.yaml"
topology_manifest="quwoquan_ops/environments/environment_topology_manifest.yaml"
if [[ ! -f "$default_cfg" ]]; then
  echo "FAIL: default service config not found: $default_cfg" >&2
  exit 1
fi
if [[ ! -f "$env_cfg" ]]; then
  echo "FAIL: env service config not found: $env_cfg" >&2
  exit 1
fi
if [[ ! -f "$topology_manifest" ]]; then
  echo "FAIL: environment topology manifest not found: $topology_manifest" >&2
  exit 1
fi
if [[ "$env_name" == prod* ]] && grep -E "test_fixtures|seedRefs|requiresSeedReset|APP_DATA_SOURCE=mock" "$env_cfg" >/dev/null; then
  echo "FAIL: production service config must not reference test seed: $env_cfg" >&2
  exit 1
fi
python3 - "$service" "$env_name" "$env_cfg" "$topology_manifest" <<'PY'
import json
import re
import sys
from pathlib import Path

service, env_name, cfg_path, topology_path = sys.argv[1:5]
text = Path(cfg_path).read_text(encoding="utf-8")
topology = json.loads(Path(topology_path).read_text(encoding="utf-8"))
env_cfg = ((topology.get("environments") or {}).get(env_name) or {})
public_bases = env_cfg.get("publicBases") or {}
allowed_tokens = {
    str(item).strip()
    for item in env_cfg.get("hostAllowlist", [])
    if str(item).strip()
}

for key, value in public_bases.items():
    if not value or value not in text:
        continue
    if key in {"api", "realtime", "productOps"}:
        raise SystemExit(
            f"{service} config must not reference {key} public base {value}"
        )

for other_env, other_cfg in (topology.get("environments") or {}).items():
    if other_env == env_name:
        continue
    for token in other_cfg.get("hostAllowlist", []) or []:
        token = str(token).strip()
        if not token or token in allowed_tokens:
            continue
        if token in text:
            raise SystemExit(
                f"{service} config leaks {other_env} host token {token}"
            )

if service == "chat-service":
    match = re.search(r"^\s*group_avatar_cdn_base_url:\s*[\"']?([^\"'\n]+)[\"']?\s*$", text, re.M)
    if not match:
        raise SystemExit("chat-service config missing group_avatar_cdn_base_url")
    value = match.group(1).strip()
    if value.startswith("${"):
        value = {
            "prod": str(public_bases.get("mediaAvatar", "")),
        }.get(env_name, value)
    if not (value.startswith("http://") or value.startswith("https://")):
        raise SystemExit("chat-service group_avatar_cdn_base_url must include http/https scheme")
    expected = str(public_bases.get("mediaAvatar", "")).strip()
    if expected and not value.startswith("${") and value != expected:
        raise SystemExit(
            f"chat-service group avatar CDN mismatch: {value} != {expected}"
        )
    if env_name in {"prod"}:
        forbidden = tuple(env_cfg.get("forbiddenHostTokens") or ()) or (
            ".example",
            ".test",
            "127.0.0.1",
            "10.0.2.2",
            "192.168.",
            "mock-cdn.example.com",
        )
        if any(token in value for token in forbidden):
            raise SystemExit("prod chat-service group avatar CDN must not use local/test host")
PY

out_dir="$(PYTHONDONTWRITEBYTECODE=1 python3 - "$env_name" "$service" <<'PY'
import sys

from quwoquan_ops.cli.lib.output_paths import service_deployment_package_dir

print(service_deployment_package_dir(sys.argv[1], sys.argv[2]))
PY
)"
rm -rf "$out_dir"
mkdir -p "$out_dir"
cp "$default_cfg" "$out_dir/default_config.yaml"
cp "$env_cfg" "$out_dir/config.yaml"
cp "$topology_manifest" "$out_dir/environment_topology_manifest.yaml"
if [[ -d "$ROOT/quwoquan_service/services/$service/configs/releases" ]]; then
  cp -R "$ROOT/quwoquan_service/services/$service/configs/releases" "$out_dir/releases"
fi
python3 - "$service" "$env_name" "$topology_manifest" "$out_dir/report.json" <<'PY'
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    import yaml  # type: ignore
except ModuleNotFoundError:
    yaml = None

service, env_name, topology_path, report_path = sys.argv[1:5]
root = Path.cwd()
module_mapping_path = root / "quwoquan_ops/environments/module_package_mapping.yaml"
catalog_path = root / "quwoquan_ops/environments/reliable_task_module_catalog.yaml"
retention_path = root / "quwoquan_ops/environments/reliable_task_retention_policy.yaml"
topology = json.loads(Path(topology_path).read_text(encoding="utf-8"))
env_topology = ((topology.get("environments") or {}).get(env_name) or {})
artifact_policy = ((env_topology.get("artifactPolicy") or {}).get("service") or {})

def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

revision = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    text=True,
    capture_output=True,
    check=False,
).stdout.strip()
if not re.fullmatch(r"[0-9a-f]{40}", revision):
    raise SystemExit("unable to resolve package git revision")

module_package = None
catalog_version = None
retention_version = None
enabled_modules = []


def _parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]


def _fallback_load_mapping(path: Path, target_env: str, target_service: str) -> tuple[Optional[str], list[str]]:
    env_indent = None
    service_indent = None
    package = None
    modules: list[str] = []
    collecting_modules = False

    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))

        env_match = re.match(r"([A-Za-z0-9_-]+):\s*$", stripped)
        if indent == 2 and env_match:
            env_indent = env_match.group(1) if env_match.group(1) == target_env else None
            service_indent = None
            collecting_modules = False
            continue
        if env_indent != target_env:
            continue

        service_match = re.match(r"([A-Za-z0-9_.-]+):\s*$", stripped)
        if indent == 4 and service_match:
            service_indent = service_match.group(1) if service_match.group(1) == target_service else None
            collecting_modules = False
            continue
        if service_indent != target_service:
            continue

        if indent <= 4:
            break

        if indent == 6 and stripped.startswith("package:"):
            package = stripped.split(":", 1)[1].strip().strip("'\"")
            collecting_modules = False
            continue
        if indent == 6 and stripped.startswith("modules:"):
            value = stripped.split(":", 1)[1].strip()
            modules = _parse_inline_list(value)
            collecting_modules = not bool(modules) and not value
            continue
        if collecting_modules and indent >= 8 and stripped.startswith("- "):
            modules.append(stripped[2:].strip().strip("'\""))
            continue
        if collecting_modules and indent <= 6:
            collecting_modules = False

    return package, modules


def _fallback_load_top_level_version(path: Path) -> Optional[object]:
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("version:"):
            value = stripped.split(":", 1)[1].strip().strip("'\"")
            if value.isdigit():
                return int(value)
            return value or None
    return None

if module_mapping_path.exists():
    if yaml is not None:
        module_mapping = yaml.safe_load(module_mapping_path.read_text(encoding="utf-8")) or {}
        package_cfg = ((module_mapping.get("environments") or {}).get(env_name) or {}).get(service)
        if package_cfg:
            module_package = package_cfg.get("package")
            enabled_modules = package_cfg.get("modules") or []
    else:
        module_package, enabled_modules = _fallback_load_mapping(module_mapping_path, env_name, service)
if catalog_path.exists():
    if yaml is not None:
        catalog_version = (yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}).get("version")
    else:
        catalog_version = _fallback_load_top_level_version(catalog_path)
if retention_path.exists():
    if yaml is not None:
        retention_version = (yaml.safe_load(retention_path.read_text(encoding="utf-8")) or {}).get("version")
    else:
        retention_version = _fallback_load_top_level_version(retention_path)

release_files = {
    path.name: digest(path)
    for path in sorted((Path(report_path).parent / "releases").glob("*.yaml"))
}

report = {
    "status": "packaged",
    "service": service,
    "env": env_name,
    "configLayout": "default+env",
    "modulePackage": module_package,
    "enabledModules": enabled_modules,
    "disabledModules": [],
    "catalogVersion": catalog_version,
    "retentionPolicyVersion": retention_version,
    "topologySchemaVersion": topology.get("schema"),
    "artifactPolicy": artifact_policy,
    "provenance": {
        "gitRevision": revision,
        "files": {
            "defaultConfig": digest(Path(report_path).parent / "default_config.yaml"),
            "environmentConfig": digest(Path(report_path).parent / "config.yaml"),
            "topologyManifest": digest(Path(topology_path)),
        },
        "releaseFiles": release_files,
    },
}
Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [[ -f "quwoquan_service/services/${service}/deploy/Dockerfile" ]]; then
  PYTHONDONTWRITEBYTECODE=1 python3 \
    quwoquan_service/scripts/runtime/generate_service_supply_chain.py \
    --service "$service" \
    --env "$env_name" \
    --package-dir "$out_dir"
fi

echo "service env package prepared: $out_dir"
