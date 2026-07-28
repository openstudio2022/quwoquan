#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
DEPLOY_TARGET_ROOT="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import deployment_work_root

print(deployment_work_root("prod-sim"))
PY
)"
QWQ_DEPLOY_WORK_ROOT="$(dirname "$DEPLOY_TARGET_ROOT")"
export QWQ_DEPLOY_WORK_ROOT
eval "$(
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/lib/public_domain_tls.py" paths \
    --target prod-sim \
    --format shell
)"
ACTION="${1:-up}"
eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_run.py" \
  --env prod --target prod-sim --action "$ACTION" --output-root "$QWQ_OUTPUT_ROOT")"
RUNTIME_CONFIG_DIR="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import deployment_render_dir

print(deployment_render_dir("prod", target="prod-sim"))
PY
)"
CACHE_DIR="${QWQ_OUTPUT_ROOT}/env/prod/local/prod-sim/cache"
STATE_DIR="${QWQ_OUTPUT_ROOT}/env/prod/local/prod-sim/process"
LOG_DIR="${QWQ_OBSERVABILITY_RUN_ROOT}/logs/service"
REPORT="${QWQ_RUN_ROOT}/prod-sim-report.json"
MEDIA_DIR="$ROOT_DIR/quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
PROD_SIM_LEGAL_STATIC_ROOT="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import legal_static_deployment_package_dir

print(
    legal_static_deployment_package_dir(
        "prod",
        target="prod-sim",
    )
    / "current"
    / "public"
)
PY
)"

eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/print_local_port_profile.py" --profile prod-sim --format shell-defaults)"

eval "$(
  PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import shlex
from urllib.parse import urlsplit

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)

bases = get_target(load_environment_topology(), "prod-sim")["publicBases"]
for name, role in (
    ("API_BASE_URL", "api"),
    ("PUBLIC_WEB_BASE_URL", "publicWeb"),
    ("LEGAL_BASE_URL", "legal"),
    ("APP_DOWNLOAD_BASE_URL", "appDownload"),
    ("PRODUCT_OPS_BASE_URL", "productOps"),
    ("MEDIA_AVATAR_BASE_URL", "mediaAvatar"),
    ("MEDIA_IMAGE_BASE_URL", "mediaImage"),
    ("MEDIA_VIDEO_BASE_URL", "mediaVideo"),
    ("MEDIA_UPLOAD_BASE_URL", "mediaUpload"),
):
    print(f"{name}={shlex.quote(str(bases[role]))}")
for name, role in (
    ("PUBLIC_API_HOST", "api"),
    ("PUBLIC_WEB_HOST", "publicWeb"),
    ("PUBLIC_PRODUCT_OPS_HOST", "productOps"),
    ("PUBLIC_CDN_HOST", "mediaImage"),
    ("PUBLIC_UPLOAD_HOST", "mediaUpload"),
):
    print(f"{name}={shlex.quote(str(urlsplit(str(bases[role])).hostname))}")
PY
)"
PUBLIC_MEDIA_HOSTS=("$PUBLIC_CDN_HOST" "$PUBLIC_UPLOAD_HOST")
API_EDGE_PORT="${PROD_SIM_GATEWAY_PORT}"
PRODUCT_OPS_PORT="${PROD_SIM_PRODUCT_OPS_PORT}"
MEDIA_EDGE_PORT="${PROD_SIM_MEDIA_EDGE_PORT}"
MEDIA_ORIGIN_PORT="${PROD_SIM_MEDIA_ORIGIN_PORT}"
CONTENT_PORT="${PROD_SIM_CONTENT_PORT}"
PRODUCT_OPS_SERVICE_PORT="${PROD_SIM_PRODUCT_OPS_SERVICE_PORT}"
MEDIA_PROCESSOR_PORT="${PROD_SIM_MEDIA_PROCESSOR_PORT}"
MEDIA_ORIGIN_BASE_URL="http://127.0.0.1:${MEDIA_ORIGIN_PORT}"
INTERNAL_API_BASE_URL="http://127.0.0.1:${CONTENT_PORT}"
INTERNAL_PRODUCT_OPS_BASE_URL="http://127.0.0.1:${PRODUCT_OPS_SERVICE_PORT}"
INTERNAL_MEDIA_BASE_URL="http://127.0.0.1:${MEDIA_PROCESSOR_PORT}"
TLS_PROXY_NAME="quwoquan_prod_sim_tls_proxy"
TLS_CADDYFILE="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import deployment_target_path

print(deployment_target_path("prod-sim", "rendered", "Caddyfile"))
PY
)"
TLS_DATA_DIR="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import deployment_target_path

print(deployment_target_path("prod-sim", "caddy-data"))
PY
)"
TLS_CONFIG_DIR="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import deployment_target_path

print(deployment_target_path("prod-sim", "caddy-config"))
PY
)"
CONTAINER_RUNTIME=""
CONTAINER_HOST_ALIAS=""

mkdir -p \
  "$RUNTIME_CONFIG_DIR" \
  "$CACHE_DIR" \
  "$STATE_DIR" \
  "$LOG_DIR" \
  "$QWQ_RUN_ROOT"

start_bg() {
  local name="$1"
  shift
  python3 - "$STATE_DIR/${name}.pid" "$STATE_DIR/${name}.pgid" \
    "$ROOT_DIR/quwoquan_ops/cli/lib/runtime_log_process.py" \
    "$LOG_DIR/${name}/local/runtime.log" "$name" "$@" <<'PY'
import os
import subprocess
import sys
from pathlib import Path

pid_path = Path(sys.argv[1])
pgid_path = Path(sys.argv[2])
wrapper = sys.argv[3]
log_path = sys.argv[4]
event = sys.argv[5]
argv = sys.argv[6:]
proc = subprocess.Popen(
    [sys.executable, wrapper, "--log-file", log_path, "--event", event, "--", *argv],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
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
  if [[ -f "$pid_file" ]]; then pid="$(<"$pid_file")"; fi
  if [[ -f "$pgid_file" ]]; then pgid="$(<"$pgid_file")"; fi
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

wait_http_range_ok() {
  local url="$1"
  local timeout="${2:-30}"
  local deadline=$((SECONDS + timeout))
  local status=""
  until [[ "$status" == "206" ]]; do
    status="$(curl -fsS -r 0-1 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 0.5
  done
}

resolve_container_runtime() {
  if [[ -n "$CONTAINER_RUNTIME" ]]; then
    return 0
  fi
  if command -v docker >/dev/null 2>&1; then
    CONTAINER_RUNTIME="docker"
    CONTAINER_HOST_ALIAS="host.docker.internal"
    return 0
  fi
  if command -v podman >/dev/null 2>&1; then
    CONTAINER_RUNTIME="podman"
    CONTAINER_HOST_ALIAS="host.containers.internal"
    return 0
  fi
  echo "[prod-sim] FAIL: docker/podman not found; cannot expose HTTPS public plane" >&2
  exit 2
}

prepare_tls_caddyfile() {
  mkdir -p "$TLS_DATA_DIR" "$TLS_CONFIG_DIR"
  cat >"$TLS_CADDYFILE" <<EOF
{
	admin off
}

(public_tls) {
	tls /etc/caddy/tls/fullchain.pem /etc/caddy/tls/privkey.pem
}

(media_cors) {
	header {
		Access-Control-Allow-Origin "*"
		Access-Control-Allow-Methods "GET, HEAD, OPTIONS"
		Access-Control-Allow-Headers "*"
		Cross-Origin-Resource-Policy "cross-origin"
	}
}

https://${PUBLIC_API_HOST}:${API_EDGE_PORT},
https://${PUBLIC_WEB_HOST}:${API_EDGE_PORT} {
	import public_tls
	handle /legal/manifest.json {
		header {
			Cache-Control "public, max-age=300"
			X-Content-Type-Options "nosniff"
		}
		root * /srv/legal
		file_server
	}
	handle /legal/* {
		header {
			Cache-Control "public, max-age=300"
			X-Content-Type-Options "nosniff"
			Content-Type "text/html; charset=utf-8"
		}
		root * /srv/legal
		file_server
	}
	handle {
		reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}
	}
}

https://${PUBLIC_PRODUCT_OPS_HOST}:${PRODUCT_OPS_PORT} {
	import public_tls
	reverse_proxy ${CONTAINER_HOST_ALIAS}:${PRODUCT_OPS_SERVICE_PORT}
}

https://${PUBLIC_CDN_HOST}:${MEDIA_EDGE_PORT},
https://${PUBLIC_UPLOAD_HOST}:${MEDIA_EDGE_PORT} {
	import public_tls
	import media_cors
	reverse_proxy ${CONTAINER_HOST_ALIAS}:${MEDIA_PROCESSOR_PORT}
}
EOF
}

stop_tls_proxy() {
  resolve_container_runtime
  "$CONTAINER_RUNTIME" rm -f "$TLS_PROXY_NAME" >/dev/null 2>&1 || true
}

start_tls_proxy() {
  resolve_container_runtime
  prepare_tls_caddyfile
  stop_tls_proxy
  "$CONTAINER_RUNTIME" run -d \
    --name "$TLS_PROXY_NAME" \
    -v "$TLS_CADDYFILE:/etc/caddy/Caddyfile:ro" \
    -v "$QWQ_PUBLIC_TLS_CERT_FILE:/etc/caddy/tls/fullchain.pem:ro" \
    -v "$QWQ_PUBLIC_TLS_KEY_FILE:/etc/caddy/tls/privkey.pem:ro" \
    -v "$PROD_SIM_LEGAL_STATIC_ROOT:/srv/legal:ro" \
    -v "$TLS_DATA_DIR:/data" \
    -v "$TLS_CONFIG_DIR:/config" \
    -p "${API_EDGE_PORT}:${API_EDGE_PORT}" \
    -p "${PRODUCT_OPS_PORT}:${PRODUCT_OPS_PORT}" \
    -p "${MEDIA_EDGE_PORT}:${MEDIA_EDGE_PORT}" \
    docker.io/library/caddy:2.8.4-alpine >/dev/null
}

wait_https_ok() {
  local host="$1"
  local port="$2"
  local path="$3"
  local timeout="${4:-30}"
  local deadline=$((SECONDS + timeout))
  until curl -fsS \
    "https://${host}:${port}${path}" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 0.5
  done
}

verify_https_legal_document() {
  local host="$1"
  local port="$2"
  local path="$3"
  local expected_title="$4"
  local content_type=""
  local body=""
  content_type="$(
    curl -fsSI \
      "https://${host}:${port}${path}" \
      | tr -d '\r' \
      | awk -F ': ' 'tolower($1) == "content-type" { print tolower($2); exit }'
  )"
  if [[ "$content_type" != "text/html; charset=utf-8" ]]; then
    echo "[prod-sim] FAIL: ${path} must return text/html; charset=utf-8, got ${content_type:-missing}" >&2
    return 1
  fi
  body="$(
    curl -fsS \
      "https://${host}:${port}${path}"
  )"
  if [[ "$body" != *"$expected_title"* ]]; then
    echo "[prod-sim] FAIL: ${path} is missing expected UTF-8 title ${expected_title}" >&2
    return 1
  fi
}

wait_https_range_ok() {
  local host="$1"
  local port="$2"
  local path="$3"
  local timeout="${4:-30}"
  local deadline=$((SECONDS + timeout))
  local status=""
  until [[ "$status" == "206" ]]; do
    status="$(
      curl -fsS \
        -r 0-1 \
        -o /dev/null \
        -w '%{http_code}' \
        "https://${host}:${port}${path}" 2>/dev/null || true
    )"
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 0.5
  done
}

write_report() {
  python3 - "$REPORT" "$API_BASE_URL" "$PUBLIC_WEB_BASE_URL" "$LEGAL_BASE_URL" "$APP_DOWNLOAD_BASE_URL" "$PRODUCT_OPS_BASE_URL" "$MEDIA_AVATAR_BASE_URL" "$MEDIA_IMAGE_BASE_URL" "$MEDIA_VIDEO_BASE_URL" "$MEDIA_UPLOAD_BASE_URL" "$MEDIA_ORIGIN_BASE_URL" <<'PY'
import json
import sys
from pathlib import Path

(
    report_path,
    api_base,
    public_web_base,
    legal_base,
    app_download_base,
    product_ops_base,
    media_avatar_base,
    media_image_base,
    media_video_base,
    media_upload_base,
    media_origin,
) = sys.argv[1:12]
payload = {
    "status": "passed",
    "target": "prod-sim",
    "gatewayBaseUrl": api_base,
    "publicWebBaseUrl": public_web_base,
    "legalBaseUrl": legal_base,
    "appDownloadBaseUrl": app_download_base,
    "productOpsBaseUrl": product_ops_base,
    "mediaAvatarBaseUrl": media_avatar_base,
    "mediaImageBaseUrl": media_image_base,
    "mediaVideoBaseUrl": media_video_base,
    "mediaUploadBaseUrl": media_upload_base,
    "mediaOriginBaseUrl": media_origin,
}
Path(report_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

status_one() {
  local name="$1"
  local host="$2"
  local port="$3"
  local path="$4"
  if [[ -f "$STATE_DIR/${name}.pid" ]] && kill -0 "$(<"$STATE_DIR/${name}.pid")" >/dev/null 2>&1; then
    echo "[prod-sim] ${name}: running pid=$(<"$STATE_DIR/${name}.pid")"
  else
    echo "[prod-sim] ${name}: not-running"
  fi
  if command -v curl >/dev/null 2>&1; then
    wait_https_ok "$host" "$port" "$path" 3 >/dev/null 2>&1 &&
      echo "[prod-sim] ${name}: health ok https://${host}:${port}${path}" ||
      echo "[prod-sim] ${name}: health pending https://${host}:${port}${path}"
  fi
}

case "$ACTION" in
  up)
    python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" package --env prod --kind legal-static
    if [[ ! -f "$PROD_SIM_LEGAL_STATIC_ROOT/legal/user-agreement" ]]; then
      echo "[prod-sim] FAIL: legal-static package missing user-agreement at $PROD_SIM_LEGAL_STATIC_ROOT" >&2
      exit 2
    fi
    stop_bg api-edge
    stop_bg product-ops
    stop_bg media-edge
    stop_bg media-origin
    stop_tls_proxy
    start_bg media-origin \
      python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_media_origin.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$MEDIA_ORIGIN_PORT" \
        --root-dir "$MEDIA_DIR" \
        --server-label prod-sim-media-origin \
        --enable-conversation-avatar-alias
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/healthz" 30
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
    wait_http_range_ok "$MEDIA_ORIGIN_BASE_URL/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" 30
    start_bg media-edge \
      python3 "$ROOT_DIR/quwoquan_ops/cli/lib/http_reverse_proxy.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$MEDIA_PROCESSOR_PORT" \
        --target-base-url "$MEDIA_ORIGIN_BASE_URL"
    wait_http_ok "$INTERNAL_MEDIA_BASE_URL/healthz" 30
    wait_http_ok "$INTERNAL_MEDIA_BASE_URL/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
    wait_http_range_ok "$INTERNAL_MEDIA_BASE_URL/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" 30
    start_bg api-edge \
      python3 "$ROOT_DIR/quwoquan_ops/cli/lib/mock_public_plane.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$CONTENT_PORT" \
        --mode api \
        --runtime-env prod \
        --legal-static-root "$PROD_SIM_LEGAL_STATIC_ROOT" \
        --gateway-base-url "$API_BASE_URL" \
        --legal-base-url "$LEGAL_BASE_URL" \
        --product-ops-base-url "$PRODUCT_OPS_BASE_URL" \
        --media-avatar-base-url "$MEDIA_AVATAR_BASE_URL" \
        --media-image-base-url "$MEDIA_IMAGE_BASE_URL" \
        --media-video-base-url "$MEDIA_VIDEO_BASE_URL" \
        --media-upload-base-url "$MEDIA_UPLOAD_BASE_URL"
    wait_http_ok "$INTERNAL_API_BASE_URL/healthz" 30
    wait_http_ok "$INTERNAL_API_BASE_URL/config/app" 30
    start_bg product-ops \
      python3 "$ROOT_DIR/quwoquan_ops/cli/lib/mock_public_plane.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$PRODUCT_OPS_SERVICE_PORT" \
        --mode product-ops \
        --runtime-env prod \
        --gateway-base-url "$API_BASE_URL" \
        --legal-base-url "$LEGAL_BASE_URL" \
        --product-ops-base-url "$PRODUCT_OPS_BASE_URL" \
        --media-avatar-base-url "$MEDIA_AVATAR_BASE_URL" \
        --media-image-base-url "$MEDIA_IMAGE_BASE_URL" \
        --media-video-base-url "$MEDIA_VIDEO_BASE_URL" \
        --media-upload-base-url "$MEDIA_UPLOAD_BASE_URL"
    wait_http_ok "$INTERNAL_PRODUCT_OPS_BASE_URL/healthz" 30
    start_tls_proxy
    wait_https_ok "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/healthz" 30
    wait_https_ok "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/config/app" 30
    wait_https_ok "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/legal/user-agreement" 30
    verify_https_legal_document "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/legal/user-agreement" "趣我圈用户协议"
    verify_https_legal_document "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/legal/privacy-policy" "趣我圈隐私政策"
    wait_https_ok "$PUBLIC_PRODUCT_OPS_HOST" "$PRODUCT_OPS_PORT" "/healthz" 30
    wait_https_ok "$PUBLIC_CDN_HOST" "$MEDIA_EDGE_PORT" "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
    wait_https_range_ok "$PUBLIC_CDN_HOST" "$MEDIA_EDGE_PORT" "/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" 30
    write_report
    echo "[prod-sim] public plane ready: $API_BASE_URL, $MEDIA_IMAGE_BASE_URL"
    ;;
  down)
    stop_bg api-edge
    stop_bg product-ops
    stop_bg media-edge
    stop_bg media-origin
    stop_tls_proxy
    rm -f "$REPORT"
    echo "[prod-sim] public plane stopped"
    ;;
  status)
    status_one api-edge "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/healthz"
    status_one product-ops "$PUBLIC_PRODUCT_OPS_HOST" "$PRODUCT_OPS_PORT" "/healthz"
    status_one media-edge "$PUBLIC_CDN_HOST" "$MEDIA_EDGE_PORT" "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"
    if command -v curl >/dev/null 2>&1; then
      wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 3 >/dev/null 2>&1 &&
        echo "[prod-sim] media-origin: health ok ${MEDIA_ORIGIN_BASE_URL}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" ||
        echo "[prod-sim] media-origin: health pending ${MEDIA_ORIGIN_BASE_URL}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"
    fi
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    exit 2
    ;;
esac
