#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [[ ! -d "$ROOT/quwoquan_app" || ! -d "$ROOT/quwoquan_service" ]]; do
  ROOT="$(dirname "$ROOT")"
  if [[ "$ROOT" == "/" ]]; then
    echo "GATE_BLOCK: cannot locate repository root from ${BASH_SOURCE[0]}" >&2
    exit 2
  fi
done
cd "$ROOT"

echo "[verify] recommendation-service contract"

DEPLOY_FILE="$ROOT/quwoquan_service/services/recommendation-service/deploy/deployment.yaml"
if [[ ! -f "$DEPLOY_FILE" ]]; then
  DEPLOY_FILE="$ROOT/quwoquan_service/services/recommendation-service/deploy/base/deployment.yaml"
fi
RUNTIME_CONTRACT="$ROOT/quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/runtime_contract.py"

if [[ ! -f "$DEPLOY_FILE" ]]; then
  echo "[verify] FAIL: missing deployment manifest: $DEPLOY_FILE" >&2
  exit 1
fi

if [[ ! -f "$RUNTIME_CONTRACT" ]]; then
  echo "[verify] FAIL: missing runtime contract module: $RUNTIME_CONTRACT" >&2
  exit 1
fi

for kw in "name: recommendation-service" "app.kubernetes.io/name: recommendation-service" "SERVICE_NAME" "value: recommendation-service" "APP_ENV" "CONFIG_VERSION" "IMAGE_VERSION" "CONFIG_ROOT"; do
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

# 行为 metadata、Go HotPath 与 Dart wire enum 必须同轨。
python3 "$ROOT/quwoquan_service/scripts/verify/consistency/verify_behavior_action_consistency.py"

# 推荐/搜索只允许共享 runtime hash 分桶；未绑定线上流量的 Product Ops
# ExperimentAssignmentFact 必须保持 default-deny 且不进入 Portal。
python3 "$ROOT/quwoquan_service/scripts/runtime/experiments/verify_experiment_single_track.py"

# 交集 kind 注册表单一真相源（Phase 0 §20d）：注册表结构 + Go evidenceKindRank 对齐。
if ! command -v python3 >/dev/null 2>&1; then
  echo "[verify] FAIL: python3 not found — intersection registry gate is mandatory"
  exit 1
fi
python3 "$ROOT/quwoquan_service/scripts/recommendation-service/recommendation/recommendation_model_release/verify_intersection_kind_registry.py" || exit 1

# 影响力 helpType 注册表单一真相源（§23 去桥接）：registry ↔ Go 表 ↔ Dart 产物 ↔ resolver ↔ 消费方 ↔ fixtures。
python3 "$ROOT/quwoquan_service/scripts/recommendation-service/recommendation/recommendation_model_release/verify_impact_help_type_registry.py" || exit 1

echo "[verify] OK: recommendation-service contract checked"
