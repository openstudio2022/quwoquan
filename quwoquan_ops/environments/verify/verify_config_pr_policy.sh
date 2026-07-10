#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] config pr policy"

# Policy (minimal, executable in local/CI):
# - If service config files changed, at least one release version snapshot must change.
# - If high-risk keys changed in service configs, risky-config docs must be updated too.

changed="$(git diff --no-renames --name-only HEAD)"
if [[ -z "$changed" ]]; then
  echo "[verify] OK: no changes against HEAD (policy skipped)"
  exit 0
fi

config_changed=0
release_changed=0
high_risk_changed=0

runtime_config_re='^quwoquan_service/services/[^/]+/configs/((default|alpha|beta|gamma|prod)/config|config)\.ya?ml$'

if echo "$changed" | rg "$runtime_config_re" >/dev/null 2>&1; then
  config_changed=1
fi
if echo "$changed" | rg '^quwoquan_service/services/[^/]+/configs/releases/v.+\.ya?ml$' >/dev/null 2>&1; then
  release_changed=1
fi

if [[ "$config_changed" -eq 1 ]]; then
  # Check high-risk key modifications in changed config files.
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    if git diff --no-renames -- "$f" | rg '^[+-].*(mode:|addrs:|addr:|password:|tls:)' >/dev/null 2>&1; then
      high_risk_changed=1
      break
    fi
  done < <(echo "$changed" | rg "$runtime_config_re")
fi

failures=0

if [[ "$config_changed" -eq 1 && "$release_changed" -eq 0 ]]; then
  echo "[verify] FAIL: service configs changed but no service-local configs/releases version file changed" >&2
  failures=$((failures + 1))
fi

if [[ "$high_risk_changed" -eq 1 ]]; then
  if ! echo "$changed" | rg 'specs/feature-tree/.*/[^/]*risky-config-gray-release/(tasks\.md|acceptance\.yaml|design\.md|spec\.md)$' >/dev/null 2>&1; then
    echo "[verify] FAIL: high-risk config keys changed but risky-config-gray-release docs were not updated" >&2
    failures=$((failures + 1))
  fi
fi

if [[ "$failures" -gt 0 ]]; then
  echo "[verify] FAIL: config pr policy check failed (failures=$failures)" >&2
  exit 1
fi

echo "[verify] OK: config pr policy checked (config_changed=$config_changed, release_changed=$release_changed, high_risk_changed=$high_risk_changed)"
