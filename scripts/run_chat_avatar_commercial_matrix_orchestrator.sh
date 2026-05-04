#!/usr/bin/env bash
# 群头像商用矩阵 Phase L/B 编排（见 commercial-e2e-matrix-runbook.md）。
# Phase C（云上 E3/E4）：仅当设置 COMMERCIAL_MATRIX_MANIFEST 时对 manifest 做机器校验，或自行下载 artifact 后填 manifest。
#
# 仅校验（不跑探针/Patrol）:
#   COMMERCIAL_MATRIX_MANIFEST=artifacts/commercial-matrix/chat-avatar/manifest.yaml \
#     bash scripts/run_chat_avatar_commercial_matrix_orchestrator.sh
#
# 完整 Phase L（默认不启 Docker）:
#   LOCAL_GAMMA_GATEWAY_BASE_URL=http://127.0.0.1:18080 \
#   bash scripts/run_chat_avatar_commercial_matrix_orchestrator.sh
#
# 启动 local-gamma 镜像栈后再跑:
#   COMMERCIAL_MATRIX_START_MIRROR=1 bash scripts/run_chat_avatar_commercial_matrix_orchestrator.sh
#
# 追加 Phase B（beta）:
#   BETA_GATEWAY_BASE_URL=http://127.0.0.1:18080 \
#   BETA_TEST_AUTH_TOKEN=... \
#   bash scripts/run_chat_avatar_commercial_matrix_orchestrator.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -n "${COMMERCIAL_MATRIX_MANIFEST:-}" ]]; then
  echo "[commercial-matrix] verify manifest only: ${COMMERCIAL_MATRIX_MANIFEST}"
  python3 scripts/verify_chat_avatar_commercial_matrix_evidence.py --manifest "${COMMERCIAL_MATRIX_MANIFEST}"
  exit $?
fi

echo "[commercial-matrix] P0 strict prereqs"
python3 scripts/check_avatar_commercial_matrix_prereqs.py --strict

LG_BASE="${LOCAL_GAMMA_GATEWAY_BASE_URL:-http://127.0.0.1:18080}"
LG_BASE="${LG_BASE%/}"
LG_MEDIA="${LOCAL_GAMMA_MEDIA_BASE_URL:-$LG_BASE}"
LG_MEDIA="${LG_MEDIA%/}"
LG_TOKEN="${LOCAL_GAMMA_TEST_AUTH_TOKEN:-local-gamma-token}"

if [[ "${COMMERCIAL_MATRIX_START_MIRROR:-0}" == "1" ]]; then
  echo "[commercial-matrix] P1 start local-gamma mirror"
  bash scripts/start_local_gamma_mirror.sh
fi

echo "[commercial-matrix] P2 gamma-proxy routing smoke"
python3 scripts/verify_gamma_public_gateway_routing.py --base-url "$LG_BASE"

echo "[commercial-matrix] P3 local-gamma T3"
python3 scripts/run_local_gamma_t3.py \
  --base-url "$LG_BASE" \
  --product-ops-base-url "${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-http://127.0.0.1:18086}" \
  --test-auth-token "$LG_TOKEN"

echo "[commercial-matrix] P4 local-gamma avatar probe + device matrix (no dry-run)"
python3 scripts/run_local_gamma_avatar_e2e.py \
  --base-url "$LG_BASE" \
  --media-base-url "$LG_MEDIA" \
  --test-auth-token "$LG_TOKEN" \
  --report "${COMMERCIAL_MATRIX_LOCAL_GAMMA_REPORT:-artifacts/local-gamma/avatar_e2e_report.json}"

if [[ -n "${BETA_GATEWAY_BASE_URL:-}" ]]; then
  BETA_BASE="${BETA_GATEWAY_BASE_URL%/}"
  BETA_MEDIA="${BETA_MEDIA_BASE_URL:-$BETA_BASE}"
  BETA_MEDIA="${BETA_MEDIA%/}"
  BETA_TOKEN="${BETA_TEST_AUTH_TOKEN:-${GAMMA_TEST_AUTH_TOKEN:-}}"
  if [[ -z "$BETA_TOKEN" ]]; then
    echo "[commercial-matrix] FAIL: BETA_GATEWAY_BASE_URL 已设但缺少 BETA_TEST_AUTH_TOKEN / GAMMA_TEST_AUTH_TOKEN" >&2
    exit 2
  fi
  echo "[commercial-matrix] P5 beta API probe"
  mkdir -p artifacts/avatar-e2e/beta
  python3 scripts/run_chat_avatar_e2e_probe.py \
    --env beta \
    --base-url "$BETA_BASE" \
    --media-base-url "$BETA_MEDIA" \
    --test-auth-token "$BETA_TOKEN" \
    --report artifacts/avatar-e2e/beta/avatar_e2e_report.json
  export API_CONTRACT_ENV=beta
  export CHAT_AVATAR_GATEWAY_BASE_URL="$BETA_BASE"
  export MEDIA_AVATAR_CDN_BASE_URL="$BETA_MEDIA"
  export GAMMA_TEST_AUTH_TOKEN="$BETA_TOKEN"
  export CHAT_AVATAR_MATRIX_ALL_DEVICES=1
  echo "[commercial-matrix] P5 beta device matrix (android)"
  python3 scripts/run_chat_avatar_device_matrix_ci.py --platform android
  echo "[commercial-matrix] P5 beta device matrix (ios)"
  python3 scripts/run_chat_avatar_device_matrix_ci.py --platform ios
fi

echo "[commercial-matrix] local phases done. E3/E4: 填入 manifest 后执行"
echo "  COMMERCIAL_MATRIX_MANIFEST=artifacts/commercial-matrix/chat-avatar/manifest.yaml bash scripts/run_chat_avatar_commercial_matrix_orchestrator.sh"
