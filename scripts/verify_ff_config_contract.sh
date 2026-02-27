#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] ff config contract"

# Minimal FF contract for config-release feature decomposition:
# 1) tasks.md contains the 3-stage gate matrix and key command names.
# 2) acceptance.yaml contains env/version/gate related acceptance text.

failures=0

tasks_files=(
  "$ROOT/specs/feature-tree/runtime/runtime-config/config-provider-layering/tasks.md"
  "$ROOT/specs/feature-tree/platform-ops-governance/config-and-reliability-governance/config-source-governance/risky-config-gray-release/tasks.md"
)

acceptance_files=(
  "$ROOT/specs/feature-tree/runtime/runtime-config/config-provider-layering/acceptance.yaml"
  "$ROOT/specs/feature-tree/platform-ops-governance/config-and-reliability-governance/config-source-governance/risky-config-gray-release/acceptance.yaml"
)

for f in "${tasks_files[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "[verify] FAIL: missing tasks file: $f" >&2
    failures=$((failures + 1))
    continue
  fi

  for kw in "/opsx-ff" "/opsx-apply" "submit-with-gate"; do
    if ! grep -n "${kw}" "$f" >/dev/null 2>&1; then
      echo "[verify] FAIL: ${f} missing gate matrix keyword: ${kw}" >&2
      failures=$((failures + 1))
    fi
  done
done

for f in "${acceptance_files[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "[verify] FAIL: missing acceptance file: $f" >&2
    failures=$((failures + 1))
    continue
  fi
  # Ensure acceptance mentions env/version/gate constraints.
  for kw in "APP_ENV" "CONFIG_VERSION" "gate"; do
    if ! grep -n "${kw}" "$f" >/dev/null 2>&1; then
      echo "[verify] WARN: ${f} does not mention ${kw} explicitly"
    fi
  done
done

if [[ "$failures" -gt 0 ]]; then
  echo "[verify] FAIL: ff config contract check failed (failures=$failures)" >&2
  exit 1
fi

echo "[verify] OK: ff config contract checked"
