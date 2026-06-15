#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
REGISTRY_PATH="${GAMMA_LOCAL_MEDIA_REGISTRY:-$ROOT_DIR/deploy/shared/media_slice_registry.json}"
BIND_HOST="${GAMMA_LOCAL_MEDIA_BIND_HOST:-0.0.0.0}"
PORT="${GAMMA_LOCAL_MEDIA_PORT:-19110}"
PUBLIC_BASE_URL="${GAMMA_LOCAL_MEDIA_PUBLIC_BASE_URL:-}"
REPORT_PATH="${GAMMA_LOCAL_MEDIA_REPORT:-$ROOT_DIR/artifacts/gamma-local-origin/report.json}"

usage() {
  cat <<EOF
Usage:
  scripts/start_gamma_local_media_origin.sh [options]

Options:
  --bind <host>             Listen host (default: ${BIND_HOST})
  --port <port>             Listen port (default: ${PORT})
  --registry <path>         Media slice registry JSON.
  --public-base-url <url>   Public URL or tunnel address visible from ECS.
  --report <path>           Write runtime report JSON.
  -h, --help                Show this help.

This starts the local media origin for the local gamma mirror (gamma-local)。
远端 gamma 已退役，仅保留本地 gamma；远端联调请走 prod-hosted 的 gray-initial 灰度实例。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bind)
      BIND_HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --registry)
      REGISTRY_PATH="${2:-}"
      shift 2
      ;;
    --public-base-url)
      PUBLIC_BASE_URL="${2:-}"
      shift 2
      ;;
    --report)
      REPORT_PATH="${2:-}"
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

mkdir -p "$(dirname "$REPORT_PATH")"
python3 - "$REPORT_PATH" "$BIND_HOST" "$PORT" "$REGISTRY_PATH" "$PUBLIC_BASE_URL" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

report_path, bind_host, port, registry_path, public_base_url = sys.argv[1:6]
payload = {
    "schemaVersion": "gamma-local-media-origin",
    "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "bindHost": bind_host,
    "port": int(port),
    "registryPath": registry_path,
    "publicBaseUrl": public_base_url,
    "recommendedEnv": {
        "GAMMA_ECS_MEDIA_ORIGIN_BASE_URL": public_base_url,
    },
}
Path(report_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "[gamma-local-media-origin] report: $REPORT_PATH"
echo "[gamma-local-media-origin] registry: $REGISTRY_PATH"
echo "[gamma-local-media-origin] listening: http://${BIND_HOST}:${PORT}"
if [[ -n "$PUBLIC_BASE_URL" ]]; then
  echo "[gamma-local-media-origin] export GAMMA_ECS_MEDIA_ORIGIN_BASE_URL=${PUBLIC_BASE_URL}"
fi

exec python3 "$ROOT_DIR/quwoquan_service/scripts/media/media_slice_server.py" \
  --bind "$BIND_HOST" \
  --port "$PORT" \
  --registry "$REGISTRY_PATH"
