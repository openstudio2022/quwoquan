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
  alpha|beta|gamma|prod-gray|prod) ;;
  *)
    echo "FAIL: --env must be one of alpha|beta|gamma|prod-gray|prod" >&2
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
if [[ ! -f "$default_cfg" ]]; then
  echo "FAIL: default service config not found: $default_cfg" >&2
  exit 1
fi
if [[ ! -f "$env_cfg" ]]; then
  echo "FAIL: env service config not found: $env_cfg" >&2
  exit 1
fi
if [[ "$env_name" == prod* ]] && grep -E "test_fixtures|seedRefs|requiresSeedReset|APP_DATA_SOURCE=mock" "$env_cfg" >/dev/null; then
  echo "FAIL: production service config must not reference test seed: $env_cfg" >&2
  exit 1
fi
if [[ "$service" == "chat-service" ]]; then
  python3 - "$env_name" "$env_cfg" <<'PY'
import re
import sys
from pathlib import Path

env_name, cfg_path = sys.argv[1:3]
text = Path(cfg_path).read_text(encoding="utf-8")
match = re.search(r"^\s*group_avatar_cdn_base_url:\s*[\"']?([^\"'\n]+)[\"']?\s*$", text, re.M)
if not match:
    raise SystemExit("chat-service config missing group_avatar_cdn_base_url")
value = match.group(1).strip()
if value.startswith("${"):
    value = {
        "prod": "https://avatar-cdn.quwoquan.com",
        "prod-gray": "https://avatar-cdn.quwoquan.com",
    }.get(env_name, value)
if not (value.startswith("http://") or value.startswith("https://")):
    raise SystemExit("chat-service group_avatar_cdn_base_url must include http/https scheme")
if env_name in {"gamma"} and not (value.endswith(".quwoquan-env.test") or ".quwoquan-env.test/" in value):
    raise SystemExit("gamma chat-service group avatar CDN must use *.quwoquan-env.test or explicit env-test domain")
if env_name in {"prod", "prod-gray"}:
    forbidden = (".example", ".test", "127.0.0.1", "10.0.2.2", "192.168.", "mock-cdn.example.com")
    if value.startswith("http://") or any(token in value for token in forbidden):
        raise SystemExit("prod/prod-gray chat-service group avatar CDN must be production HTTPS domain")
PY
fi

out_dir="artifacts/service-env-packages/${service}/${env_name}"
rm -rf "$out_dir"
mkdir -p "$out_dir"
cp "$default_cfg" "$out_dir/default_config.yaml"
cp "$env_cfg" "$out_dir/config.yaml"
python3 - "$service" "$env_name" "$out_dir/report.json" <<'PY'
import json
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ModuleNotFoundError:
    yaml = None

service, env_name, report_path = sys.argv[1:4]
root = Path.cwd()
module_mapping_path = root / "deploy/shared/module_package_mapping.yaml"
catalog_path = root / "deploy/shared/reliable_task_module_catalog.yaml"
retention_path = root / "deploy/shared/reliable_task_retention_policy.yaml"

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


def _fallback_load_mapping(path: Path, target_env: str, target_service: str) -> tuple[str | None, list[str]]:
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


def _fallback_load_top_level_version(path: Path) -> int | str | None:
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
}
Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "service env package prepared: $out_dir"
