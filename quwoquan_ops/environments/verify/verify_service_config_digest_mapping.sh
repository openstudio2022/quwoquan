#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

checked=0
schema_count=0
for schema in quwoquan_service/services/*/config/schema.yaml \
  quwoquan_service/control-plane/platform-ops/config/schema.yaml; do
  [[ -f "$schema" ]] || continue
  schema_count=$((schema_count + 1))
  owner="$(dirname "$(dirname "$schema")")"
  service="$(basename "$owner")"
  if [[ "$service" == "platform-ops" ]]; then
    service="platform-ops-service"
  fi
  for env_name in alpha beta gamma prod; do
    output="$tmp_dir/${service}-${env_name}.yaml"
    PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/render_runtime_config.py \
      --env "$env_name" --workload "$service" --output "$output" >/dev/null
    PYTHONDONTWRITEBYTECODE=1 python3 - "$output" <<'PY'
import hashlib
import re
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
version = str(((payload.get("config") or {}).get("version") or ""))
if not re.fullmatch(r"sha256:[0-9a-f]{64}", version):
    raise SystemExit(f"invalid digest-derived CONFIG_VERSION: {path}: {version}")
PY
    checked=$((checked + 1))
  done
done

[[ "$schema_count" -gt 0 ]] || { echo "FAIL: no runtime config schema found" >&2; exit 1; }
expected=$((schema_count * 4))
[[ "$checked" -eq "$expected" ]] || {
  echo "FAIL: rendered config count=$checked, want $expected from $schema_count owners" >&2
  exit 1
}
echo "OK: $checked autonomous environment configs have digest-derived CONFIG_VERSION"
