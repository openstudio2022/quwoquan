#!/usr/bin/env bash
# Patrol UAT test host 的 Xcode build phase 入口：把 build-profile trust envelope 嵌进
# 宿主 bundle。嵌入实现与生产 Runner 共用 build_embed_runtime_config_trust.py。
#
# 宿主的 configuration 命名不带 buildProfile flavor 后缀，因此 build profile 由启动链经
# QWQ_APP_BUILD_PROFILE 显式交出，不从 configuration 名反推；缺席即判否，不猜一个默认值。
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACKCTL_PYTHON_RESOLVER="$APP_DIR/scripts/ios/build_resolve_stackctl_python.sh"
TRUST_BLOCKER="APP.LAUNCH.runtime_config_trust_missing"

BUILD_PROFILE="${QWQ_APP_BUILD_PROFILE:-}"
if [[ -z "$BUILD_PROFILE" ]]; then
  echo "[patrol-runtime-config] GATE_BLOCK: QWQ_APP_BUILD_PROFILE is required; the UAT launch chain must declare the host build profile." >&2
  exit 2
fi

RUNTIME_TRUST_PATH="${QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH:-}"
if [[ -z "$RUNTIME_TRUST_PATH" ]]; then
  echo "[patrol-runtime-config] GATE_BLOCK: $TRUST_BLOCKER: build-profile runtime trust envelope is required for the UAT test host." >&2
  echo "[patrol-runtime-config] launch through stackctl smoke app-content-uat; the canonical host launcher materializes the trust envelope." >&2
  exit 2
fi

if [[ -z "${TARGET_BUILD_DIR:-}" || -z "${UNLOCALIZED_RESOURCES_FOLDER_PATH:-}" ]]; then
  echo "[patrol-runtime-config] GATE_BLOCK: $TRUST_BLOCKER: Xcode resource output is required to materialize the trust envelope." >&2
  exit 2
fi

RUNTIME_PYTHON="$(bash "$STACKCTL_PYTHON_RESOLVER")" || {
  echo "[patrol-runtime-config] GATE_BLOCK: build requires Python 3.10+ with PyYAML." >&2
  exit 2
}

if ! "$RUNTIME_PYTHON" "$APP_DIR/scripts/ios/build_embed_runtime_config_trust.py" \
  "$RUNTIME_TRUST_PATH" "$BUILD_PROFILE" \
  "$TARGET_BUILD_DIR" "$UNLOCALIZED_RESOURCES_FOLDER_PATH"; then
  echo "[patrol-runtime-config] GATE_BLOCK: $TRUST_BLOCKER: build-profile runtime trust envelope is invalid." >&2
  exit 2
fi

echo "[patrol-runtime-config] embeddedTrustEnvelope=1 buildProfile=${BUILD_PROFILE} embeddedRuntimePackage=0" >&2
