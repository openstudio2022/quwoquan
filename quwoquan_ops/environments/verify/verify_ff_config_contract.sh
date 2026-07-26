#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

echo "[verify] ff config spec contract"

spec_files=(
  "$ROOT/specs/feature-tree/runtime/runtime-config/config-provider-layering/spec.md"
  "$ROOT/specs/feature-tree/platform-ops-governance/config-and-reliability-governance/config-source-governance/spec.md"
)

failures=0
for spec in "${spec_files[@]}"; do
  if [[ ! -f "$spec" ]]; then
    echo "[verify] FAIL: missing spec: $spec" >&2
    failures=$((failures + 1))
    continue
  fi
  for token in "REQ-" "GWT-"; do
    if ! grep -nF -- "$token" "$spec" >/dev/null; then
      echo "[verify] FAIL: $spec missing $token" >&2
      failures=$((failures + 1))
    fi
  done
done

if [[ "$failures" -gt 0 ]]; then
  echo "[verify] FAIL: ff config spec contract ($failures)" >&2
  exit 1
fi
echo "[verify] OK: ff config spec contract"
