#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STATE_DIR="$ROOT_DIR/state/local/alpha_stack"
MEDIA_DIR="$ROOT_DIR/quwoquan_service/contracts/metadata/_shared/test_fixtures/media"

eval "$(python3 "$ROOT_DIR/agent_ops/deploy/print_local_port_profile.py" --profile alpha-local --format shell-defaults)"

ACTION="${1:-up}"
API_EDGE_PORT="${API_EDGE_PORT}"
PRODUCT_OPS_PORT="${PRODUCT_OPS_PORT}"
MEDIA_EDGE_PORT="${MEDIA_EDGE_PORT}"
MEDIA_ORIGIN_PORT="${MEDIA_ORIGIN_PORT}"
API_BASE_URL="http://127.0.0.1:${API_EDGE_PORT}"
PRODUCT_OPS_BASE_URL="http://127.0.0.1:${PRODUCT_OPS_PORT}"
MEDIA_BASE_URL="http://127.0.0.1:${MEDIA_EDGE_PORT}"
MEDIA_ORIGIN_BASE_URL="http://127.0.0.1:${MEDIA_ORIGIN_PORT}"

mkdir -p "$STATE_DIR"

start_bg() {
  local name="$1"
  shift
  python3 - "$STATE_DIR/${name}.pid" "$STATE_DIR/${name}.pgid" "$STATE_DIR/${name}.log" "$@" <<'PY'
import os
import subprocess
import sys
from pathlib import Path

pid_path = Path(sys.argv[1])
pgid_path = Path(sys.argv[2])
log_path = Path(sys.argv[3])
argv = sys.argv[4:]

log_path.parent.mkdir(parents=True, exist_ok=True)
with log_path.open("wb", buffering=0) as log:
    proc = subprocess.Popen(
        argv,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    pid_path.write_text(f"{proc.pid}\n", encoding="utf-8")
    pgid_path.write_text(f"{os.getpgid(proc.pid)}\n", encoding="utf-8")
PY
}

stop_bg() {
  local name="$1"
  local pid_file="$STATE_DIR/${name}.pid"
  local pgid_file="$STATE_DIR/${name}.pgid"
  local pid=""
  local pgid=""
  if [[ -f "$pid_file" ]]; then pid="$(cat "$pid_file")"; fi
  if [[ -f "$pgid_file" ]]; then pgid="$(cat "$pgid_file")"; fi
  if [[ -n "$pgid" ]] && kill -0 "-$pgid" >/dev/null 2>&1; then
    kill -TERM "-$pgid" >/dev/null 2>&1 || true
    local deadline=$((SECONDS + 15))
    while kill -0 "-$pgid" >/dev/null 2>&1; do
      if (( SECONDS >= deadline )); then
        kill -KILL "-$pgid" >/dev/null 2>&1 || true
        break
      fi
      sleep 0.2
    done
  elif [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$pid_file" "$pgid_file"
}

wait_http_ok() {
  local url="$1"
  local timeout="${2:-30}"
  local deadline=$((SECONDS + timeout))
  until curl -fsS "$url" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 0.5
  done
}

write_report() {
  python3 - "$STATE_DIR/report.json" "$API_BASE_URL" "$PRODUCT_OPS_BASE_URL" "$MEDIA_BASE_URL" "$MEDIA_ORIGIN_BASE_URL" <<'PY'
import json
import sys
from pathlib import Path

report_path, api_base, product_ops_base, media_base, media_origin = sys.argv[1:6]
payload = {
    "status": "passed",
    "target": "alpha-local",
    "gatewayBaseUrl": api_base,
    "productOpsBaseUrl": product_ops_base,
    "mediaBaseUrl": media_base,
    "mediaOriginBaseUrl": media_origin,
}
Path(report_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

status_one() {
  local name="$1"
  local url="$2"
  if [[ -f "$STATE_DIR/${name}.pid" ]] && kill -0 "$(cat "$STATE_DIR/${name}.pid")" >/dev/null 2>&1; then
    echo "[alpha] ${name}: running pid=$(cat "$STATE_DIR/${name}.pid")"
  else
    echo "[alpha] ${name}: not-running"
  fi
  if command -v curl >/dev/null 2>&1; then
    wait_http_ok "$url" 3 >/dev/null 2>&1 && echo "[alpha] ${name}: health ok ${url}" || echo "[alpha] ${name}: health pending ${url}"
  fi
}

case "$ACTION" in
  up)
    stop_bg api-edge
    stop_bg product-ops
    stop_bg media-edge
    stop_bg media-origin
    start_bg media-origin \
      python3 "$ROOT_DIR/agent_ops/deploy/lib/alpha_media_origin.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$MEDIA_ORIGIN_PORT" \
        --root-dir "$MEDIA_DIR"
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/healthz" 30
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/avatar/conversation/conv_002/v1/mock.png" 30
    start_bg media-edge \
      python3 "$ROOT_DIR/agent_ops/deploy/lib/http_reverse_proxy.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$MEDIA_EDGE_PORT" \
        --target-base-url "$MEDIA_ORIGIN_BASE_URL"
    wait_http_ok "$MEDIA_BASE_URL/healthz" 30
    wait_http_ok "$MEDIA_BASE_URL/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
    wait_http_ok "$MEDIA_BASE_URL/media/avatar/conversation/conv_002/v1/mock.png" 30
    start_bg api-edge \
      python3 "$ROOT_DIR/agent_ops/deploy/lib/mock_public_plane.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$API_EDGE_PORT" \
        --mode api \
        --runtime-env alpha \
        --data-source mock \
        --gateway-base-url "$API_BASE_URL" \
        --product-ops-base-url "$PRODUCT_OPS_BASE_URL" \
        --media-base-url "$MEDIA_BASE_URL"
    wait_http_ok "$API_BASE_URL/healthz" 30
    wait_http_ok "$API_BASE_URL/v1/config/app" 30
    start_bg product-ops \
      python3 "$ROOT_DIR/agent_ops/deploy/lib/mock_public_plane.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$PRODUCT_OPS_PORT" \
        --mode product-ops \
        --runtime-env alpha \
        --data-source mock \
        --gateway-base-url "$API_BASE_URL" \
        --product-ops-base-url "$PRODUCT_OPS_BASE_URL" \
        --media-base-url "$MEDIA_BASE_URL"
    wait_http_ok "$PRODUCT_OPS_BASE_URL/healthz" 30
    write_report
    echo "[alpha] mock public plane ready: $API_BASE_URL, $MEDIA_BASE_URL"
    ;;
  down)
    stop_bg api-edge
    stop_bg product-ops
    stop_bg media-edge
    stop_bg media-origin
    rm -f "$STATE_DIR/report.json"
    echo "[alpha] mock public plane stopped"
    ;;
  status)
    status_one api-edge "$API_BASE_URL/healthz"
    status_one product-ops "$PRODUCT_OPS_BASE_URL/healthz"
    status_one media-edge "$MEDIA_BASE_URL/healthz"
    status_one media-origin "$MEDIA_ORIGIN_BASE_URL/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    exit 2
    ;;
esac
