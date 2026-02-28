#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] recommendation-service contract"

DEPLOY_FILE="$ROOT/deploy/service/recommendation-service/deployment.yaml"
RUNTIME_CONTRACT="$ROOT/quwoquan_service/services/rec-model-service/runtime_contract.py"

if [[ ! -f "$DEPLOY_FILE" ]]; then
  echo "[verify] FAIL: missing deployment manifest: $DEPLOY_FILE" >&2
  exit 1
fi

if [[ ! -f "$RUNTIME_CONTRACT" ]]; then
  echo "[verify] FAIL: missing runtime contract module: $RUNTIME_CONTRACT" >&2
  exit 1
fi

for kw in "name: recommendation-service" "app: recommendation-service" "SERVICE_NAME" "value: recommendation-service" "APP_ENV" "CONFIG_VERSION" "IMAGE_VERSION" "CONFIG_ROOT"; do
  if ! grep -n "$kw" "$DEPLOY_FILE" >/dev/null 2>&1; then
    echo "[verify] FAIL: deploy manifest missing keyword: $kw" >&2
    exit 1
  fi
done

for kw in "VALID_APP_ENVS" "EXPECTED_SERVICE_NAME" "APP_ENV" "SERVICE_NAME" "CONFIG_VERSION" "IMAGE_VERSION" "CONFIG_ROOT" "raise RuntimeError"; do
  if ! grep -n "$kw" "$RUNTIME_CONTRACT" >/dev/null 2>&1; then
    echo "[verify] FAIL: runtime contract missing keyword: $kw" >&2
    exit 1
  fi
done

echo "[verify] OK: recommendation-service contract checked"
