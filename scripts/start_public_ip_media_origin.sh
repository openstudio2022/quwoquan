#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_BIND_HOST="${PUBLIC_MEDIA_BIND_HOST:-0.0.0.0}"
LOCAL_PORT="${PUBLIC_MEDIA_LOCAL_PORT:-18098}"
PUBLIC_PORT="${PUBLIC_MEDIA_PUBLIC_PORT:-$LOCAL_PORT}"
PUBLIC_SCHEME="${PUBLIC_MEDIA_PUBLIC_SCHEME:-http}"
PUBLIC_IP_OVERRIDE="${PUBLIC_MEDIA_PUBLIC_IP:-}"
ORIGIN_REPORT_PATH="${PUBLIC_MEDIA_ORIGIN_REPORT:-$ROOT_DIR/artifacts/gamma-local-origin/origin-report.json}"
SESSION_REPORT_PATH="${PUBLIC_MEDIA_SESSION_REPORT:-$ROOT_DIR/artifacts/gamma-local-origin/public-ip-session.json}"

usage() {
  cat <<EOF
Usage:
  scripts/start_public_ip_media_origin.sh [options]

Options:
  --bind <host>          Local bind host (default: ${LOCAL_BIND_HOST})
  --port <port>          Local listen port (default: ${LOCAL_PORT})
  --public-port <port>   Public exposed port (default: same as local port)
  --scheme <http|https>  Public scheme used in generated URL (default: ${PUBLIC_SCHEME})
  --public-ip <ip>       Override auto-detected public IP
  --report <path>        Session report path
  -h, --help             Show this help

This wrapper resolves the current public IP on this machine each time, then
starts the media origin with PUBLIC_BASE_URL=${PUBLIC_SCHEME}://<public-ip>:<public-port>.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bind)
      LOCAL_BIND_HOST="${2:-}"
      shift 2
      ;;
    --port)
      LOCAL_PORT="${2:-}"
      shift 2
      ;;
    --public-port)
      PUBLIC_PORT="${2:-}"
      shift 2
      ;;
    --scheme)
      PUBLIC_SCHEME="${2:-}"
      shift 2
      ;;
    --public-ip)
      PUBLIC_IP_OVERRIDE="${2:-}"
      shift 2
      ;;
    --report)
      SESSION_REPORT_PATH="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

mkdir -p "$(dirname "$SESSION_REPORT_PATH")"

python3 - "$SESSION_REPORT_PATH" "$PUBLIC_IP_OVERRIDE" "$LOCAL_PORT" "$PUBLIC_PORT" "$LOCAL_BIND_HOST" "$PUBLIC_SCHEME" <<'PY'
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

report_path, public_ip_override, local_port, public_port, bind_host, scheme = sys.argv[1:7]

def fetch_public_ip() -> str:
    candidates = (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://checkip.amazonaws.com",
    )
    results: list[str] = []
    for url in candidates:
        with urlopen(url, timeout=8) as resp:
            value = resp.read().decode("utf-8", errors="replace").strip()
            if value:
                results.append(value)
    unique = []
    for item in results:
        if item not in unique:
            unique.append(item)
    if not unique:
        raise SystemExit("failed to resolve public ip")
    if len(unique) != 1:
        raise SystemExit(f"inconsistent public ip answers: {unique}")
    return unique[0]

def run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, timeout=5).strip()
    except Exception:
        return ""

public_ip = (public_ip_override or "").strip() or fetch_public_ip()
gateway_dump = run(["route", "-n", "get", "default"])
local_ip = run(["ipconfig", "getifaddr", "en0"]) or run(["ipconfig", "getifaddr", "en1"])
gateway = ""
for line in gateway_dump.splitlines():
    if line.strip().startswith("gateway:"):
        gateway = line.split(":", 1)[1].strip()
        break

public_base_url = f"{scheme}://{public_ip}:{public_port}"
payload = {
    "schemaVersion": "public-ip-media-origin-session.v1",
    "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "publicIp": public_ip,
    "publicBaseUrl": public_base_url,
    "localBindHost": bind_host,
    "localPort": int(local_port),
    "publicPort": int(public_port),
    "localIp": local_ip,
    "gateway": gateway,
    "notes": [
        "If gateway/localIp are private addresses, inbound access still depends on router hotspot port forwarding or direct public routability.",
        "This script only resolves the dynamic public IP and starts the local server; it cannot force ISP/router to open inbound traffic.",
    ],
}
Path(report_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False))
PY

SESSION_JSON="$(python3 - "$SESSION_REPORT_PATH" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print(payload["publicBaseUrl"])
print(payload["publicIp"])
print(payload["localIp"])
print(payload["gateway"])
PY
)"

PUBLIC_BASE_URL="$(printf '%s\n' "$SESSION_JSON" | sed -n '1p')"
PUBLIC_IP="$(printf '%s\n' "$SESSION_JSON" | sed -n '2p')"
LOCAL_IP="$(printf '%s\n' "$SESSION_JSON" | sed -n '3p')"
GATEWAY="$(printf '%s\n' "$SESSION_JSON" | sed -n '4p')"

echo "[public-ip-media-origin] public_ip=${PUBLIC_IP}"
echo "[public-ip-media-origin] public_base_url=${PUBLIC_BASE_URL}"
echo "[public-ip-media-origin] local_ip=${LOCAL_IP:-<unknown>}"
echo "[public-ip-media-origin] gateway=${GATEWAY:-<unknown>}"
echo "[public-ip-media-origin] report=${SESSION_REPORT_PATH}"
echo "[public-ip-media-origin] note: direct inbound access still requires router/hotspot/ISP path to allow ${PUBLIC_PORT}->${LOCAL_PORT}"

exec bash "$ROOT_DIR/scripts/start_gamma_local_media_origin.sh" \
  --bind "$LOCAL_BIND_HOST" \
  --port "$LOCAL_PORT" \
  --public-base-url "$PUBLIC_BASE_URL" \
  --report "$ORIGIN_REPORT_PATH"
