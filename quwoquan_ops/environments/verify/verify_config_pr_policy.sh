#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] config pr policy"

# Policy (minimal, executable in local/CI):
# - 服务 config schema 或四环境差异发生变化时，不要求手工 release snapshot；发布包会派生摘要。
# - 高风险键变化必须同步特性树规格或设计，且旧 configs/ 路径不得回潮。

changed="$({
  git diff --no-renames --diff-filter=ACMRTUXB --name-only HEAD
  git ls-files --others --exclude-standard
} | awk 'NF && !seen[$0]++')"
if [[ -z "$changed" ]]; then
  echo "[verify] OK: no changes against HEAD (policy skipped)"
  exit 0
fi

config_changed=0
high_risk_changed=0

runtime_config_re='^quwoquan_service/(services/[^/]+|control-plane/platform-ops)/(config/schema|environments/(alpha|beta|gamma|prod)/config)\.ya?ml$'

if echo "$changed" | grep -E "$runtime_config_re" >/dev/null 2>&1; then
  config_changed=1
fi
if [[ "$config_changed" -eq 1 ]]; then
  # Check high-risk key modifications in changed config files.
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    if git diff --no-renames -- "$f" | grep -E '^[+-].*(mode:|addrs:|addr:|password:|tls:)' >/dev/null 2>&1; then
      high_risk_changed=1
      break
    fi
  done < <(echo "$changed" | grep -E "$runtime_config_re")
fi

failures=0

if find quwoquan_service/services quwoquan_service/control-plane/platform-ops \
  -type d -name configs -print -quit | grep -q . >/dev/null 2>&1; then
  echo "[verify] FAIL: retired service configs/** path returned" >&2
  failures=$((failures + 1))
fi

if [[ "$high_risk_changed" -eq 1 ]]; then
  if ! echo "$changed" | grep -E '^specs/feature-tree/(.*/)?(spec|design)\.md$' >/dev/null 2>&1; then
    echo "[verify] FAIL: high-risk config keys changed but feature-tree spec/design was not updated" >&2
    failures=$((failures + 1))
  fi
fi

if [[ "$failures" -gt 0 ]]; then
  echo "[verify] FAIL: config pr policy check failed (failures=$failures)" >&2
  exit 1
fi

echo "[verify] OK: config pr policy checked (config_changed=$config_changed, high_risk_changed=$high_risk_changed)"
