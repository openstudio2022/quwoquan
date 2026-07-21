#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/quwoquan/deploy}"
ACTION="${1:-up}"
eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_run.py" \
  --env alpha --target alpha-local --action "$ACTION" --output-root "$QWQ_OUTPUT_ROOT")"
STATE_DIR="$QWQ_OUTPUT_ROOT/env/alpha/local/alpha-local/process"
RUNTIME_LOG_DIR="$QWQ_OBSERVABILITY_RUN_ROOT/logs/service"
PKI_STATE_DIR="$QWQ_DEPLOY_WORK_ROOT/alpha-local/certificates"
MEDIA_DIR="$ROOT_DIR/quwoquan_service/contracts/metadata/_shared/test_fixtures/media"
LEGAL_STATIC_ROOT="$(PYTHONPATH="$ROOT_DIR" PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from quwoquan_ops.cli.lib.output_paths import legal_static_deployment_package_dir

print(legal_static_deployment_package_dir("alpha") / "current" / "public")
PY
)"

eval "$(python3 "$ROOT_DIR/quwoquan_ops/cli/print_local_port_profile.py" --profile alpha-local --format shell-defaults)"

PUBLIC_HOST_SETUP_MODE="${QWQ_ALPHA_LOCAL_PUBLIC_HOST_SETUP:-require}"
MACOS_KEYCHAIN_TRUST_MODE="${QWQ_ALPHA_LOCAL_MACOS_KEYCHAIN_TRUST:-auto}"
MACOS_KEYCHAIN_TRUST_MARKER="$PKI_STATE_DIR/macos_login_keychain_trust.sha256"
PUBLIC_API_HOST="alpha-api.quwoquan-env.test"
PUBLIC_PRODUCT_OPS_HOST="alpha-product-ops.quwoquan-env.test"
PUBLIC_MEDIA_HOSTS=(
  "alpha-avatar.quwoquan-env.test"
  "alpha-image.quwoquan-env.test"
  "alpha-video.quwoquan-env.test"
  "alpha-upload.quwoquan-env.test"
)
PUBLIC_HOSTS=(
  "$PUBLIC_API_HOST"
  "$PUBLIC_PRODUCT_OPS_HOST"
  "${PUBLIC_MEDIA_HOSTS[@]}"
)
LOCAL_API_HOST="alpha-api.localhost"
LOCAL_PRODUCT_OPS_HOST="alpha-product-ops.localhost"
LOCAL_MEDIA_HOSTS=(
  "alpha-avatar.localhost"
  "alpha-image.localhost"
  "alpha-video.localhost"
  "alpha-upload.localhost"
)
API_EDGE_PORT="${API_EDGE_PORT}"
PRODUCT_OPS_PORT="${PRODUCT_OPS_PORT}"
MEDIA_EDGE_PORT="${MEDIA_EDGE_PORT}"
MEDIA_ORIGIN_PORT="${MEDIA_ORIGIN_PORT}"
CONTENT_PORT="${CONTENT_PORT}"
PRODUCT_OPS_SERVICE_PORT="${PRODUCT_OPS_SERVICE_PORT}"
MEDIA_PROCESSOR_PORT="${MEDIA_PROCESSOR_PORT}"
API_BASE_URL="https://${PUBLIC_API_HOST}:${API_EDGE_PORT}"
PRODUCT_OPS_BASE_URL="https://${PUBLIC_PRODUCT_OPS_HOST}:${PRODUCT_OPS_PORT}"
MEDIA_BASE_URL="https://alpha-image.quwoquan-env.test:${MEDIA_EDGE_PORT}"
MEDIA_ORIGIN_BASE_URL="http://127.0.0.1:${MEDIA_ORIGIN_PORT}"
INTERNAL_API_BASE_URL="http://127.0.0.1:${CONTENT_PORT}"
INTERNAL_PRODUCT_OPS_BASE_URL="http://127.0.0.1:${PRODUCT_OPS_SERVICE_PORT}"
INTERNAL_MEDIA_BASE_URL="http://127.0.0.1:${MEDIA_PROCESSOR_PORT}"
# TLS profile/topology lives in quwoquan_ops/environments; generated key
# material is durable PKI state and never belongs to rebuildable output.
TLS_CA_DIR="$PKI_STATE_DIR"
TLS_ROOT_KEY="$TLS_CA_DIR/root.key"
TLS_ROOT_CERT="$TLS_CA_DIR/root.crt"
TLS_DIR="$PKI_STATE_DIR/tls"
TLS_OPENSSL_CONFIG="$TLS_DIR/alpha-local-openssl.cnf"
TLS_LEAF_KEY="$TLS_DIR/alpha-local.key"
TLS_LEAF_CSR="$TLS_DIR/alpha-local.csr"
TLS_LEAF_CERT="$TLS_DIR/alpha-local.crt"

mkdir -p "$STATE_DIR" "$RUNTIME_LOG_DIR" "$PKI_STATE_DIR"

start_bg() {
  local name="$1"
  shift
  python3 - "$STATE_DIR/${name}.pid" "$STATE_DIR/${name}.pgid" \
    "$ROOT_DIR/quwoquan_ops/cli/lib/runtime_log_process.py" \
    "$RUNTIME_LOG_DIR/${name}/local/runtime.log" "$name" "$@" <<'PY'
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

stop_repo_listener_on_port() {
  local port="$1"
  local pids=""
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi
  pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  local pid=""
  local stopped_any=0
  for pid in $pids; do
    local command_line=""
    command_line="$(ps -p "$pid" -ww -o command= 2>/dev/null || true)"
    case "$command_line" in
      *"$ROOT_DIR/quwoquan_ops/cli/lib/mock_public_plane.py"*|\
      *"$ROOT_DIR/quwoquan_ops/cli/lib/local_media_origin.py"*|\
      *"$ROOT_DIR/quwoquan_ops/cli/lib/http_reverse_proxy.py"*|\
      *"$ROOT_DIR/quwoquan_ops/cli/lib/tls_reverse_proxy.py"*)
        kill "$pid" >/dev/null 2>&1 || true
        stopped_any=1
        ;;
      *)
        ;;
    esac
  done
  if [[ "$stopped_any" != "1" ]]; then
    return 0
  fi
  local deadline=$((SECONDS + 5))
  while lsof -nP -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      break
    fi
    sleep 0.2
  done
}

stop_alpha_reserved_listeners() {
  local port=""
  for port in \
    "$API_EDGE_PORT" \
    "$PRODUCT_OPS_PORT" \
    "$MEDIA_EDGE_PORT" \
    "$MEDIA_ORIGIN_PORT" \
    "$CONTENT_PORT" \
    "$PRODUCT_OPS_SERVICE_PORT" \
    "$MEDIA_PROCESSOR_PORT"; do
    stop_repo_listener_on_port "$port"
  done
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

ensure_legal_static_package() {
  python3 "$ROOT_DIR/quwoquan_ops/cli/legal_static.py" package --env alpha >/dev/null
  if [[ ! -f "$LEGAL_STATIC_ROOT/legal/user-agreement" ]]; then
    echo "[alpha] FAIL: legal-static package missing user-agreement at $LEGAL_STATIC_ROOT" >&2
    return 1
  fi
}

assert_distinct_http_body_sha256() {
  local url_a="$1"
  local url_b="$2"
  local hash_a hash_b
  hash_a="$(curl -fsS "$url_a" | shasum -a 256 | awk '{print $1}')"
  hash_b="$(curl -fsS "$url_b" | shasum -a 256 | awk '{print $1}')"
  if [[ -z "$hash_a" || -z "$hash_b" || "$hash_a" == "$hash_b" ]]; then
    echo "[alpha] FAIL: expected distinct conv_grid avatar bodies for:" >&2
    echo "  $url_a" >&2
    echo "  $url_b" >&2
    return 1
  fi
  echo "[alpha] conv_grid avatar sha256 distinct: conv_grid_3=${hash_a:0:12} conv_grid_8=${hash_b:0:12}"
}

stop_tls_proxy() {
  stop_bg edge-api
  stop_bg edge-product-ops
  stop_bg edge-media
}

prepare_tls_material() {
  if ! command -v openssl >/dev/null 2>&1; then
    echo "[alpha] FAIL: openssl not found; cannot generate local TLS certificates" >&2
    exit 2
  fi
  mkdir -p "$TLS_CA_DIR" "$TLS_DIR"
  if [[ ! -f "$TLS_ROOT_CERT" || ! -f "$TLS_ROOT_KEY" ]]; then
    openssl genrsa -out "$TLS_ROOT_KEY" 2048 >/dev/null 2>&1
    openssl req -x509 -new -nodes \
      -key "$TLS_ROOT_KEY" \
      -sha256 \
      -days 3650 \
      -subj "/CN=quwoquan alpha local root" \
      -out "$TLS_ROOT_CERT" >/dev/null 2>&1
  fi
  cat >"$TLS_OPENSSL_CONFIG" <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = alpha-api.localhost

[v3_req]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${PUBLIC_API_HOST}
DNS.2 = ${LOCAL_API_HOST}
DNS.3 = ${PUBLIC_PRODUCT_OPS_HOST}
DNS.4 = ${LOCAL_PRODUCT_OPS_HOST}
DNS.5 = ${PUBLIC_MEDIA_HOSTS[0]}
DNS.6 = ${PUBLIC_MEDIA_HOSTS[1]}
DNS.7 = ${PUBLIC_MEDIA_HOSTS[2]}
DNS.8 = ${PUBLIC_MEDIA_HOSTS[3]}
DNS.9 = ${LOCAL_MEDIA_HOSTS[0]}
DNS.10 = ${LOCAL_MEDIA_HOSTS[1]}
DNS.11 = ${LOCAL_MEDIA_HOSTS[2]}
DNS.12 = ${LOCAL_MEDIA_HOSTS[3]}
DNS.13 = localhost
IP.1 = 127.0.0.1
IP.2 = 10.0.2.2
IP.3 = ::1
EOF
  openssl req -new \
    -keyout "$TLS_LEAF_KEY" \
    -out "$TLS_LEAF_CSR" \
    -nodes \
    -config "$TLS_OPENSSL_CONFIG" >/dev/null 2>&1
  openssl x509 -req \
    -in "$TLS_LEAF_CSR" \
    -CA "$TLS_ROOT_CERT" \
    -CAkey "$TLS_ROOT_KEY" \
    -CAcreateserial \
    -out "$TLS_LEAF_CERT" \
    -days 825 \
    -sha256 \
    -extensions v3_req \
    -extfile "$TLS_OPENSSL_CONFIG" >/dev/null 2>&1
}

start_tls_proxy() {
  prepare_tls_material
  stop_tls_proxy
  start_bg edge-api \
    python3 "$ROOT_DIR/quwoquan_ops/cli/lib/tls_reverse_proxy.py" \
      --listen-host 127.0.0.1 \
      --listen-port "$API_EDGE_PORT" \
      --target-base-url "$INTERNAL_API_BASE_URL" \
      --cert-file "$TLS_LEAF_CERT" \
      --key-file "$TLS_LEAF_KEY"
  start_bg edge-product-ops \
    python3 "$ROOT_DIR/quwoquan_ops/cli/lib/tls_reverse_proxy.py" \
      --listen-host 127.0.0.1 \
      --listen-port "$PRODUCT_OPS_PORT" \
      --target-base-url "$INTERNAL_PRODUCT_OPS_BASE_URL" \
      --cert-file "$TLS_LEAF_CERT" \
      --key-file "$TLS_LEAF_KEY"
  start_bg edge-media \
    python3 "$ROOT_DIR/quwoquan_ops/cli/lib/tls_reverse_proxy.py" \
      --listen-host 127.0.0.1 \
      --listen-port "$MEDIA_EDGE_PORT" \
      --target-base-url "$INTERNAL_MEDIA_BASE_URL" \
      --cert-file "$TLS_LEAF_CERT" \
      --key-file "$TLS_LEAF_KEY"
}

wait_https_ok() {
  local host="$1"
  local port="$2"
  local path="$3"
  local timeout="${4:-30}"
  local deadline=$((SECONDS + timeout))
  until curl -fsS "https://${host}:${port}${path}" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 0.5
  done
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

wait_https_with_ca_ok() {
  local host="$1"
  local port="$2"
  local path="$3"
  local timeout="${4:-30}"
  local deadline=$((SECONDS + timeout))
  until curl -fsS \
    --cacert "$TLS_ROOT_CERT" \
    "https://${host}:${port}${path}" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 0.5
  done
}

wait_https_with_ca_range_ok() {
  local host="$1"
  local port="$2"
  local path="$3"
  local timeout="${4:-30}"
  local deadline=$((SECONDS + timeout))
  local status=""
  until [[ "$status" == "206" ]]; do
    status="$(
      curl -fsS \
        --cacert "$TLS_ROOT_CERT" \
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

admin_shell() {
  local command="$1"
  if sudo -n true >/dev/null 2>&1; then
    sudo sh -c "$command"
    return 0
  fi
  if [[ "${QWQ_ALPHA_LOCAL_ALLOW_ADMIN_PROMPT:-1}" == "1" ]] &&
     [[ "$(uname -s)" == "Darwin" ]] &&
     command -v osascript >/dev/null 2>&1; then
    local quoted
    quoted="$(python3 - "$command" <<'PY'
import json
import sys

print(json.dumps(sys.argv[1]))
PY
)"
    osascript -e "do shell script ${quoted} with administrator privileges"
    return 0
  fi
  echo "[alpha] GATE_BLOCK: alpha HTTPS public hosts require /etc/hosts management." >&2
  echo "[alpha] Run once with admin rights, or set QWQ_ALPHA_LOCAL_ALLOW_ADMIN_PROMPT=1 to allow the macOS password prompt." >&2
  return 1
}

flush_host_cache() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    dscacheutil -flushcache >/dev/null 2>&1 || true
    killall -HUP mDNSResponder >/dev/null 2>&1 || true
  fi
}

ensure_public_hosts_mapping() {
  local tmp_hosts
  tmp_hosts="$(mktemp "${TMPDIR:-/tmp}/quwoquan-alpha-hosts.XXXXXX")"
  python3 - "$tmp_hosts" "${PUBLIC_HOSTS[@]}" <<'PY'
import re
import sys
from pathlib import Path

out_path = Path(sys.argv[1])
hosts = sys.argv[2:]
hosts_path = Path("/etc/hosts")
begin = "# BEGIN quwoquan alpha local public plane"
end = "# END quwoquan alpha local public plane"
block = f"{begin}\n127.0.0.1 {' '.join(hosts)}\n::1 {' '.join(hosts)}\n{end}\n"

current = hosts_path.read_text(encoding="utf-8", errors="replace")
next_text = re.sub(
    rf"{re.escape(begin)}.*?{re.escape(end)}\n?",
    "",
    current,
    flags=re.S,
).rstrip() + "\n\n" + block
out_path.write_text(next_text, encoding="utf-8")
PY
  chmod 0644 "$tmp_hosts"

  local needs_update=0
  if ! cmp -s "$tmp_hosts" /etc/hosts; then
    needs_update=1
  fi
  if (( needs_update == 1 )); then
    admin_shell "/bin/cp '$tmp_hosts' /etc/hosts"
    flush_host_cache
  fi
  rm -f "$tmp_hosts"

  python3 - "${PUBLIC_HOSTS[@]}" <<'PY'
import socket
import sys

failed = []
for host in sys.argv[1:]:
    resolved = sorted({item[4][0] for item in socket.getaddrinfo(host, None)})
    if not any(address.startswith("127.") or address == "::1" for address in resolved):
        failed.append(f"{host} -> {', '.join(resolved)}")
if failed:
    print("[alpha] GATE_BLOCK: alpha public hosts do not resolve to loopback:", file=sys.stderr)
    for item in failed:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)
PY
}

local_root_ca_fingerprint_sha256() {
  openssl x509 -in "$TLS_ROOT_CERT" -noout -fingerprint -sha256 2>/dev/null \
    | cut -d= -f2 | tr -d ':' | tr '[:upper:]' '[:lower:]'
}

macos_login_keychain_trust_is_current() {
  local expected recorded
  expected="$(local_root_ca_fingerprint_sha256)"
  [[ -n "$expected" && -f "$MACOS_KEYCHAIN_TRUST_MARKER" ]] || return 1
  recorded="$(tr -d '[:space:]' < "$MACOS_KEYCHAIN_TRUST_MARKER")"
  [[ "$recorded" == "$expected" ]]
}

install_macos_login_keychain_trust() {
  if [[ "$MACOS_KEYCHAIN_TRUST_MODE" == "skip" ]]; then
    echo "[alpha] macOS login keychain trust skipped (QWQ_ALPHA_LOCAL_MACOS_KEYCHAIN_TRUST=skip)"
    return 0
  fi
  if macos_login_keychain_trust_is_current; then
    echo "[alpha] macOS login keychain already trusts local root CA (marker ok)"
    return 0
  fi
  if ! command -v security >/dev/null 2>&1; then
    return 0
  fi
  security add-trusted-cert \
    -r trustRoot \
    -p ssl \
    -k "$HOME/Library/Keychains/login.keychain-db" \
    "$TLS_ROOT_CERT" || {
      echo "[alpha] GATE_BLOCK: failed to trust alpha local root CA in the user keychain: $TLS_ROOT_CERT" >&2
      return 1
    }
  local_root_ca_fingerprint_sha256 > "$MACOS_KEYCHAIN_TRUST_MARKER"
  echo "[alpha] macOS login keychain trust installed for local root CA"
}

install_requested_simulator_root_ca() {
  local simulator_udid="${QWQ_IOS_SIMULATOR_UDID:-}"
  if [[ -z "$simulator_udid" ]]; then
    if [[ "${QWQ_IOS_SIMULATOR_CA_REQUIRED:-0}" == "1" ]]; then
      echo "[alpha] GATE_BLOCK: iOS Simulator root-CA installation requires an explicit UDID." >&2
      echo "[alpha] Repair: launch with QWQ_IOS_SIMULATOR_UDID=<simulator-udid>, or run:" >&2
      echo "[alpha]   python3 $ROOT_DIR/quwoquan_ops/cli/lib/local_target_tls.py install-ios-simulator-ca --target alpha-local --simulator-udid <simulator-udid>" >&2
      return 1
    fi
    echo "[alpha] iOS Simulator CA install not requested; device UAT must pass an explicit Simulator UDID"
    return 0
  fi
  python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_target_tls.py" \
    install-ios-simulator-ca \
    --target alpha-local \
    --simulator-udid "$simulator_udid"
}

install_local_ca_trust() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    return 0
  fi
  install_macos_login_keychain_trust
  install_requested_simulator_root_ca
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
  local host="$2"
  local port="$3"
  local path="$4"
  if [[ -f "$STATE_DIR/${name}.pid" ]] && kill -0 "$(cat "$STATE_DIR/${name}.pid")" >/dev/null 2>&1; then
    echo "[alpha] ${name}: running pid=$(cat "$STATE_DIR/${name}.pid")"
  else
    echo "[alpha] ${name}: not-running"
  fi
  if command -v curl >/dev/null 2>&1; then
    wait_https_ok "$host" "$port" "$path" 3 >/dev/null 2>&1 &&
      echo "[alpha] ${name}: health ok https://${host}:${port}${path}" ||
      echo "[alpha] ${name}: health pending https://${host}:${port}${path}"
  fi
}

case "$ACTION" in
  up)
    stop_bg api-edge
    stop_bg product-ops
    stop_bg media-edge
    stop_bg media-origin
    stop_tls_proxy
    stop_alpha_reserved_listeners
    start_bg media-origin \
      python3 "$ROOT_DIR/quwoquan_ops/cli/lib/local_media_origin.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$MEDIA_ORIGIN_PORT" \
        --root-dir "$MEDIA_DIR" \
        --server-label alpha-media-origin \
        --enable-conversation-avatar-alias
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/healthz" 30
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
    wait_http_range_ok "$MEDIA_ORIGIN_BASE_URL/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" 30
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/avatar/conversation/conv_002/v1/mock.png" 30
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png" 30
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/avatar/s/archived-avatar/conversation/conv_grid_3/v1/mock.png" 30
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/avatar/s/archived-avatar/conversation/conv_grid_8/v1/mock.png" 30
    assert_distinct_http_body_sha256 \
      "$MEDIA_ORIGIN_BASE_URL/media/avatar/s/archived-avatar/conversation/conv_grid_3/v1/mock.png" \
      "$MEDIA_ORIGIN_BASE_URL/media/avatar/s/archived-avatar/conversation/conv_grid_8/v1/mock.png"
    wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png" 30
    start_bg media-edge \
      python3 "$ROOT_DIR/quwoquan_ops/cli/lib/http_reverse_proxy.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$MEDIA_PROCESSOR_PORT" \
        --target-base-url "$MEDIA_ORIGIN_BASE_URL"
    wait_http_ok "$INTERNAL_MEDIA_BASE_URL/healthz" 30
    wait_http_ok "$INTERNAL_MEDIA_BASE_URL/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
    wait_http_range_ok "$INTERNAL_MEDIA_BASE_URL/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" 30
    wait_http_ok "$INTERNAL_MEDIA_BASE_URL/media/avatar/conversation/conv_002/v1/mock.png" 30
    wait_http_ok "$INTERNAL_MEDIA_BASE_URL/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png" 30
    wait_http_ok "$INTERNAL_MEDIA_BASE_URL/media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png" 30
    ensure_legal_static_package
    start_bg api-edge \
      python3 "$ROOT_DIR/quwoquan_ops/cli/lib/mock_public_plane.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$CONTENT_PORT" \
        --mode api \
        --runtime-env alpha \
        --data-source mock \
        --gateway-base-url "$API_BASE_URL" \
        --product-ops-base-url "$PRODUCT_OPS_BASE_URL" \
        --media-base-url "$MEDIA_BASE_URL" \
        --legal-static-root "$LEGAL_STATIC_ROOT"
    wait_http_ok "$INTERNAL_API_BASE_URL/healthz" 30
    wait_http_ok "$INTERNAL_API_BASE_URL/config/app" 30
    wait_http_ok "$INTERNAL_API_BASE_URL/legal/user-agreement" 30
    start_bg product-ops \
      python3 "$ROOT_DIR/quwoquan_ops/cli/lib/mock_public_plane.py" \
        --listen-host 127.0.0.1 \
        --listen-port "$PRODUCT_OPS_SERVICE_PORT" \
        --mode product-ops \
        --runtime-env alpha \
        --data-source mock \
        --gateway-base-url "$API_BASE_URL" \
        --product-ops-base-url "$PRODUCT_OPS_BASE_URL" \
        --media-base-url "$MEDIA_BASE_URL" \
        --legal-static-root "$LEGAL_STATIC_ROOT"
    wait_http_ok "$INTERNAL_PRODUCT_OPS_BASE_URL/healthz" 30
    start_tls_proxy
    if [[ "$PUBLIC_HOST_SETUP_MODE" == "skip" ]]; then
      wait_https_with_ca_ok "localhost" "$API_EDGE_PORT" "/healthz" 30
      wait_https_with_ca_ok "localhost" "$API_EDGE_PORT" "/config/app" 30
      wait_https_with_ca_ok "localhost" "$API_EDGE_PORT" "/legal/user-agreement" 30
      wait_https_with_ca_ok "localhost" "$PRODUCT_OPS_PORT" "/healthz" 30
      wait_https_with_ca_ok "localhost" "$MEDIA_EDGE_PORT" "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
      wait_https_with_ca_range_ok "localhost" "$MEDIA_EDGE_PORT" "/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" 30
      wait_https_with_ca_ok "localhost" "$MEDIA_EDGE_PORT" "/media/avatar/conversation/conv_002/v1/mock.png" 30
      wait_https_with_ca_ok "localhost" "$MEDIA_EDGE_PORT" "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png" 30
      wait_https_with_ca_ok "localhost" "$MEDIA_EDGE_PORT" "/media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png" 30
    else
      ensure_public_hosts_mapping
      install_local_ca_trust
      if [[ "$MACOS_KEYCHAIN_TRUST_MODE" == "skip" ]]; then
        wait_https_with_ca_ok "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/healthz" 30
        wait_https_with_ca_ok "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/config/app" 30
        wait_https_with_ca_ok "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/legal/user-agreement" 30
        wait_https_with_ca_ok "$PUBLIC_PRODUCT_OPS_HOST" "$PRODUCT_OPS_PORT" "/healthz" 30
        wait_https_with_ca_ok "alpha-image.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
        wait_https_with_ca_range_ok "alpha-video.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" 30
        wait_https_with_ca_ok "alpha-avatar.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/avatar/conversation/conv_002/v1/mock.png" 30
        wait_https_with_ca_ok "alpha-avatar.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png" 30
        wait_https_with_ca_ok "alpha-avatar.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png" 30
      else
        wait_https_ok "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/healthz" 30
        wait_https_ok "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/config/app" 30
        wait_https_ok "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/legal/user-agreement" 30
        wait_https_ok "$PUBLIC_PRODUCT_OPS_HOST" "$PRODUCT_OPS_PORT" "/healthz" 30
        wait_https_ok "alpha-image.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 30
        wait_https_range_ok "alpha-video.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/video/s/video-primary-0001/post/video-content-0001/source.mp4" 30
        wait_https_ok "alpha-avatar.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/avatar/conversation/conv_002/v1/mock.png" 30
        wait_https_ok "alpha-avatar.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png" 30
        wait_https_ok "alpha-avatar.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png" 30
      fi
    fi
    write_report
    echo "[alpha] mock public plane ready: $API_BASE_URL, $MEDIA_BASE_URL"
    ;;
  down)
    stop_bg api-edge
    stop_bg product-ops
    stop_bg media-edge
    stop_bg media-origin
    stop_tls_proxy
    stop_alpha_reserved_listeners
    rm -f "$STATE_DIR/report.json"
    echo "[alpha] mock public plane stopped"
    ;;
  status)
    status_one api-edge "$PUBLIC_API_HOST" "$API_EDGE_PORT" "/healthz"
    status_one product-ops "$PUBLIC_PRODUCT_OPS_HOST" "$PRODUCT_OPS_PORT" "/healthz"
    status_one media-edge "alpha-image.quwoquan-env.test" "$MEDIA_EDGE_PORT" "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"
    if command -v curl >/dev/null 2>&1; then
      wait_http_ok "$MEDIA_ORIGIN_BASE_URL/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" 3 >/dev/null 2>&1 &&
        echo "[alpha] media-origin: health ok ${MEDIA_ORIGIN_BASE_URL}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png" ||
        echo "[alpha] media-origin: health pending ${MEDIA_ORIGIN_BASE_URL}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"
    fi
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    exit 2
    ;;
esac
