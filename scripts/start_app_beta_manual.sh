#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/quwoquan_app"
ASSISTANT_SERVICE_DIR="$ROOT_DIR/quwoquan_service/services/assistant-service"
LOG_DIR="$ROOT_DIR/tmp/app_beta_manual"
MANIFEST="$ROOT_DIR/quwoquan_service/contracts/metadata/_shared/test_fixtures/app_beta_seed_manifest.json"
ASSISTANT_APP_CONFIG="$ROOT_DIR/quwoquan_app/assistant/config.json"

ASSISTANT_PORT="${ASSISTANT_PORT:-18087}"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
MEDIA_PORT="${MEDIA_PORT:-18088}"
GATEWAY_BASE_URL_EXPLICIT=0
if [[ -n "${GATEWAY_BASE_URL:-}" ]]; then
  GATEWAY_BASE_URL_EXPLICIT=1
else
  GATEWAY_BASE_URL="http://127.0.0.1:${GATEWAY_PORT}"
fi
LOCAL_PUBLIC_HOST="${LOCAL_PUBLIC_HOST:-}"
MEDIA_AVATAR_CDN_BASE_URL="${MEDIA_AVATAR_CDN_BASE_URL:-}"
MEDIA_IMAGE_CDN_BASE_URL="${MEDIA_IMAGE_CDN_BASE_URL:-}"
MEDIA_VIDEO_CDN_BASE_URL="${MEDIA_VIDEO_CDN_BASE_URL:-}"
MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL:-}"
APP_CURRENT_USER_ID="${APP_CURRENT_USER_ID:-fixture_user_current}"
ASSISTANT_SEED_REFS="${ASSISTANT_SEED_REFS:-assistant_p0_core}"
FLUTTER_DEVICE_ID="${FLUTTER_DEVICE_ID:-}"
SKIP_APP=0
KILL_EXISTING=1
RESTART_STACK=1
CLEAN_ENV=0

BETA_MANUAL_LABEL="app-beta-manual"
BETA_MANUAL_STACK_NAME="app_beta_manual"
BETA_MANUAL_LOG_DIR="$LOG_DIR"
BETA_MANUAL_OWNER_ID="${BETA_MANUAL_STACK_NAME}-$$-$(date +%s)"
export BETA_MANUAL_OWNER_ID
source "$ROOT_DIR/scripts/lib/beta_manual_lifecycle.sh"

usage() {
  cat <<EOF
Usage:
  scripts/start_app_beta_manual.sh [options]

Default:
  Restart the local beta cloud stack, then start the Flutter app.

Options:
  --device-id <id>           Flutter device id for manual beta run.
  --gateway-base-url <url>   Gateway URL injected into Flutter app.
                             iOS simulator default: http://127.0.0.1:${GATEWAY_PORT}
                             Android emulator usually: http://10.0.2.2:${GATEWAY_PORT}
  --local-public-host <host>  Host visible from the App device for gateway/media.
  --media-base-url <url>      Media CDN/upload base URL injected into Flutter app.
                             Defaults to http://<local-public-host>:${MEDIA_PORT}
  --skip-app                 Start/check beta cloud stack only; do not start Flutter.
  --restart                  Stop a managed previous stack before starting (default on).
  --clean-env                Remove runtime pid/env state before starting.
  --kill-existing            Reclaim beta ports by killing listeners (default on).
  -h, --help                 Show this help.

This is the single local beta manual entrypoint. With no arguments it stops
the previous managed beta stack, starts assistant-service, starts the unified
local beta gateway for business fixture routes, checks key cloud routes, and
then starts the Flutter app.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device-id)
      FLUTTER_DEVICE_ID="${2:-}"
      shift 2
      ;;
    --gateway-base-url)
      GATEWAY_BASE_URL="${2:-}"
      GATEWAY_BASE_URL_EXPLICIT=1
      shift 2
      ;;
    --local-public-host)
      LOCAL_PUBLIC_HOST="${2:-}"
      shift 2
      ;;
    --media-base-url)
      MEDIA_AVATAR_CDN_BASE_URL="${2:-}"
      MEDIA_IMAGE_CDN_BASE_URL="${2:-}"
      MEDIA_VIDEO_CDN_BASE_URL="${2:-}"
      MEDIA_UPLOAD_BASE_URL="${2:-}"
      shift 2
      ;;
    --skip-app)
      SKIP_APP=1
      shift
      ;;
    --kill-existing)
      KILL_EXISTING=1
      shift
      ;;
    --restart)
      RESTART_STACK=1
      shift
      ;;
    --clean-env)
      CLEAN_ENV=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

resolve_assistant_model_env() {
  python3 - "$ROOT_DIR" "$ASSISTANT_APP_CONFIG" <<'PY'
import json
import os
import re
import shlex
import sys
from pathlib import Path

root = Path(sys.argv[1])
config_path = Path(sys.argv[2])
home = Path(os.environ.get("HOME", ""))

def parse_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            out[key] = value
    return out

def merge_envs() -> dict[str, str]:
    merged: dict[str, str] = {}
    for candidate in [
        home / ".moltbot" / ".env",
        home / ".clawdbot" / ".env",
        root / "quwoquan_app" / "assistant" / ".env",
        root / "quwoquan_app" / "assistant" / "config" / ".env",
    ]:
        merged.update(parse_dotenv(candidate))
    for key, value in os.environ.items():
        if value.strip():
            merged[key] = value.strip()
    return merged

def aliases(name: str) -> list[str]:
    if name == "MIMO_API_KEY":
        return ["MIMO_API_KEY", "PERSONAL_ASSISTANT_MIMO_API_KEY"]
    if name == "PERSONAL_ASSISTANT_MIMO_API_KEY":
        return ["PERSONAL_ASSISTANT_MIMO_API_KEY", "MIMO_API_KEY"]
    return [name]

def resolve_from_moltbot(env_name: str) -> str:
    if env_name not in {"MIMO_API_KEY", "PERSONAL_ASSISTANT_MIMO_API_KEY"}:
        return ""
    for candidate in [
        home / ".moltbot" / "moltbot.json",
        home / ".moltbot" / "clawdbot.json",
        home / ".moltbot" / "agents" / "main" / "agent" / "models.json",
        home / ".clawdbot" / "moltbot.json",
        home / ".clawdbot" / "clawdbot.json",
        home / ".clawdbot" / "agents" / "main" / "agent" / "models.json",
    ]:
        if not candidate.is_file():
            continue
        try:
            decoded = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        for path in [
            ("skills", "mimo", "apiKey"),
            ("models", "providers", "mimo", "apiKey"),
        ]:
            value = decoded
            for part in path:
                value = value.get(part) if isinstance(value, dict) else None
            if isinstance(value, str) and value.strip() and not value.strip().startswith("${"):
                return value.strip()
    return ""

def resolve_key(raw: str, env: dict[str, str]) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    match = re.fullmatch(r"\$\{([A-Z0-9_]+)\}", raw)
    if not match:
        return raw
    env_name = match.group(1)
    for name in aliases(env_name):
        value = env.get(name, "").strip()
        if value:
            return value
    return resolve_from_moltbot(env_name)

if not config_path.is_file():
    print(f"echo 'GATE_BLOCK: assistant model config not found: {config_path}' >&2")
    print("exit 2")
    raise SystemExit(0)

config = json.loads(config_path.read_text(encoding="utf-8"))
env = merge_envs()
providers = (((config.get("models") or {}).get("providers")) or {})
model_pref = (((config.get("agents") or {}).get("defaults") or {}).get("model") or {})
preferred_refs = []
primary = str(model_pref.get("primary") or "").strip()
if primary:
    preferred_refs.append(primary)
preferred_refs.extend(str(item).strip() for item in model_pref.get("fallbacks") or [] if str(item).strip())
rank = {ref: idx for idx, ref in enumerate(preferred_refs)}

configs = []
for provider_id, provider in providers.items():
    if not isinstance(provider, dict):
        continue
    base_url = str(provider.get("baseUrl") or "").strip()
    api_key = resolve_key(str(provider.get("apiKey") or ""), env)
    if not base_url or not api_key:
        continue
    for model in provider.get("models") or []:
        if not isinstance(model, dict):
            continue
        model_id = str(model.get("id") or "").strip()
        if not model_id:
            continue
        ref = f"{provider_id}/{model_id}"
        configs.append((rank.get(ref, 9999), ref, str(provider_id), model_id, base_url, api_key))

if not configs:
    print("echo 'GATE_BLOCK: no usable assistant model config resolved from quwoquan_app/assistant/config.json' >&2")
    print("exit 2")
    raise SystemExit(0)

_, ref, provider_id, model_id, base_url, api_key = sorted(configs, key=lambda item: (item[0], item[1]))[0]
print(f"ASSISTANT_MODEL_PROVIDER={shlex.quote('openai_compatible')}")
print(f"ASSISTANT_MODEL_BASE_URL={shlex.quote(base_url)}")
print(f"ASSISTANT_MODEL_MODEL={shlex.quote(model_id)}")
print("ASSISTANT_MODEL_API_KEY_ENV=ASSISTANT_BETA_RESOLVED_MODEL_API_KEY")
print(f"ASSISTANT_BETA_RESOLVED_MODEL_API_KEY={shlex.quote(api_key)}")
print(f"ASSISTANT_BETA_MODEL_REF={shlex.quote(ref)}")
print(f"ASSISTANT_BETA_MODEL_SOURCE_PROVIDER={shlex.quote(provider_id)}")
PY
}

eval "$(resolve_assistant_model_env)"

if [[ -z "${ASSISTANT_BETA_RESOLVED_MODEL_API_KEY:-}" ]]; then
  echo "GATE_BLOCK: no assistant beta model key resolved from environment config." >&2
  exit 2
fi

BETA_MANUAL_KILL_EXISTING="$KILL_EXISTING"
beta_manual_init
ASSISTANT_LOG="$LOG_DIR/assistant-service-beta.log"
GATEWAY_LOG="$LOG_DIR/app-beta-gateway.log"
MEDIA_LOG="$LOG_DIR/app-beta-media.log"
MEDIA_DIR="$LOG_DIR/media"
REPORT="$LOG_DIR/app-beta-manual-report.json"

detect_device_kind() {
  local device_id="$1"
  if [[ -z "$device_id" ]]; then
    echo "ios_or_macos"
    return
  fi
  if [[ "$device_id" == emulator-* || "$device_id" == *"Android SDK"* ]]; then
    echo "android_emulator"
    return
  fi
  if command -v adb >/dev/null 2>&1 && adb -s "$device_id" get-state >/dev/null 2>&1; then
    echo "android_physical"
    return
  fi
  echo "ios_or_macos"
}

DEVICE_KIND="$(detect_device_kind "$FLUTTER_DEVICE_ID")"
ADB_REVERSE_ENABLED=0
if [[ -z "$LOCAL_PUBLIC_HOST" ]]; then
  case "$DEVICE_KIND" in
    android_emulator) LOCAL_PUBLIC_HOST="10.0.2.2" ;;
    *) LOCAL_PUBLIC_HOST="127.0.0.1" ;;
  esac
fi
if [[ "$GATEWAY_BASE_URL_EXPLICIT" == "0" ]]; then
  GATEWAY_BASE_URL="http://${LOCAL_PUBLIC_HOST}:${GATEWAY_PORT}"
fi
MEDIA_AVATAR_CDN_BASE_URL="${MEDIA_AVATAR_CDN_BASE_URL:-http://${LOCAL_PUBLIC_HOST}:${MEDIA_PORT}}"
MEDIA_IMAGE_CDN_BASE_URL="${MEDIA_IMAGE_CDN_BASE_URL:-http://${LOCAL_PUBLIC_HOST}:${MEDIA_PORT}}"
MEDIA_VIDEO_CDN_BASE_URL="${MEDIA_VIDEO_CDN_BASE_URL:-http://${LOCAL_PUBLIC_HOST}:${MEDIA_PORT}}"
MEDIA_UPLOAD_BASE_URL="${MEDIA_UPLOAD_BASE_URL:-http://${LOCAL_PUBLIC_HOST}:${MEDIA_PORT}}"

python3 scripts/verify_app_seed_manifests.py
bash scripts/build_app_env_package.sh --env beta >/dev/null
bash scripts/build_service_env_package.sh --service assistant-service --env beta >/dev/null

if [[ "$RESTART_STACK" == "1" || "$CLEAN_ENV" == "1" ]]; then
  echo "[app-beta-manual] restarting managed beta stack before launch"
  beta_manual_stop_stack "$CLEAN_ENV"
  beta_manual_init
fi

: >"$BETA_MANUAL_STATE_DIR/stack.env"
beta_manual_record_metadata "stack" "$BETA_MANUAL_STACK_NAME"
beta_manual_record_metadata "controller_pid" "$$"
beta_manual_record_metadata "owner_id" "$BETA_MANUAL_OWNER_ID"
beta_manual_record_metadata "assistant_port" "$ASSISTANT_PORT"
beta_manual_record_metadata "gateway_port" "$GATEWAY_PORT"
beta_manual_record_metadata "gateway_base_url" "$GATEWAY_BASE_URL"
beta_manual_record_metadata "flutter_device_id" "$FLUTTER_DEVICE_ID"
beta_manual_record_metadata "device_kind" "$DEVICE_KIND"
beta_manual_record_metadata "local_public_host" "$LOCAL_PUBLIC_HOST"
beta_manual_record_metadata "media_port" "$MEDIA_PORT"
beta_manual_record_metadata "media_avatar_cdn_base_url" "$MEDIA_AVATAR_CDN_BASE_URL"

cleanup() {
  trap - EXIT INT TERM
  beta_manual_stop_stack "$CLEAN_ENV" "$BETA_MANUAL_OWNER_ID"
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

beta_manual_ensure_port_available "$ASSISTANT_PORT" "assistant-service"
beta_manual_ensure_port_available "$GATEWAY_PORT" "gateway"
beta_manual_ensure_port_available "$MEDIA_PORT" "media-static"

echo "[app-beta-manual] logs: $LOG_DIR"
echo "[app-beta-manual] model: ${ASSISTANT_BETA_MODEL_REF:-unknown} (${ASSISTANT_MODEL_BASE_URL})"
mkdir -p "$MEDIA_DIR/media/avatar" "$MEDIA_DIR/media/image" "$MEDIA_DIR/media/video"
python3 - "$MEDIA_DIR" <<'PY'
import base64
import sys
from pathlib import Path

root = Path(sys.argv[1])
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)
for rel in ["media/avatar/beta-avatar.png", "media/image/beta-cover.png"]:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
(root / "media/video").mkdir(parents=True, exist_ok=True)
(root / "media/video/beta-sample.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
PY
echo "[app-beta-manual] starting local media static server on :$MEDIA_PORT"
beta_manual_start_process \
  "media-static" \
  "$MEDIA_LOG" \
  "$ROOT_DIR" \
  python3 -m http.server "$MEDIA_PORT" --bind 127.0.0.1 --directory "$MEDIA_DIR"
beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_PORT}/media/avatar/beta-avatar.png" "media avatar fixture" 30 || { echo "media log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_PORT}/media/image/beta-cover.png" "media image fixture" 30 || { echo "media log: $MEDIA_LOG" >&2; exit 1; }
if [[ "$DEVICE_KIND" == "android_physical" && -n "$FLUTTER_DEVICE_ID" && "$LOCAL_PUBLIC_HOST" == "127.0.0.1" && -x "$(command -v adb 2>/dev/null || true)" ]]; then
  adb -s "$FLUTTER_DEVICE_ID" reverse "tcp:${GATEWAY_PORT}" "tcp:${GATEWAY_PORT}" >/dev/null 2>&1 || true
  adb -s "$FLUTTER_DEVICE_ID" reverse "tcp:${MEDIA_PORT}" "tcp:${MEDIA_PORT}" >/dev/null 2>&1 || true
  ADB_REVERSE_ENABLED=1
fi
echo "[app-beta-manual] starting assistant-service beta on :$ASSISTANT_PORT"
beta_manual_start_process \
  "assistant-service" \
  "$ASSISTANT_LOG" \
  "$ASSISTANT_SERVICE_DIR" \
  env \
    APP_ENV=beta \
    ASSISTANT_SERVICE_ADDR=":${ASSISTANT_PORT}" \
    ASSISTANT_SCENARIO_SEED_REFS="$ASSISTANT_SEED_REFS" \
    ASSISTANT_MODEL_PROVIDER="$ASSISTANT_MODEL_PROVIDER" \
    ASSISTANT_MODEL_BASE_URL="$ASSISTANT_MODEL_BASE_URL" \
    ASSISTANT_MODEL_MODEL="$ASSISTANT_MODEL_MODEL" \
    ASSISTANT_MODEL_API_KEY_ENV="$ASSISTANT_MODEL_API_KEY_ENV" \
    ASSISTANT_BETA_RESOLVED_MODEL_API_KEY="$ASSISTANT_BETA_RESOLVED_MODEL_API_KEY" \
    go run ./cmd/api

beta_manual_wait_http_ok "http://127.0.0.1:${ASSISTANT_PORT}/healthz" "assistant-service" 60 || {
  echo "assistant log: $ASSISTANT_LOG" >&2
  echo "gateway log: $GATEWAY_LOG" >&2
  exit 1
}

echo "[app-beta-manual] starting unified local beta gateway on :$GATEWAY_PORT"
beta_manual_start_process \
  "gateway" \
  "$GATEWAY_LOG" \
  "$ROOT_DIR" \
  python3 scripts/dev_assistant_beta_gateway.py \
    --listen-host 127.0.0.1 \
    --listen-port "$GATEWAY_PORT" \
    --upstream-host 127.0.0.1 \
    --upstream-port "$ASSISTANT_PORT" \
    --avatar-cdn-base-url "$MEDIA_AVATAR_CDN_BASE_URL" \
    --image-cdn-base-url "$MEDIA_IMAGE_CDN_BASE_URL" \
    --video-cdn-base-url "$MEDIA_VIDEO_CDN_BASE_URL"

beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/healthz" "gateway" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/assistant/skill-subscriptions" "assistant route" 60 || { echo "assistant log: $ASSISTANT_LOG" >&2; echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/config/app" "app config fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/content/feed" "content fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/chat/inbox" "chat fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/chat/contacts" "chat contacts fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/chat/conversations" "chat conversations fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${MEDIA_PORT}/media/avatar/beta-avatar.png" "host media avatar route" 30 || { echo "media log: $MEDIA_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/circles" "circle fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/circles/fixture_circle_photo/feed" "circle feed fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/user/profile" "user fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/me" "current user fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/user/personas/active" "active persona fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/user/settings/appearance" "appearance fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/content/profile-subjects/fixture_user_current/posts" "profile posts fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/users/fixture_user_current/works" "profile works fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/users/fixture_user_current/circles" "profile circles fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/user/profile-subjects/fixture_user_current/relationship/capability" "relationship capability fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/entity/homepages" "entity fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/integration/locations/pois" "integration fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/app-messages" "notification fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }
beta_manual_wait_http_ok "http://127.0.0.1:${GATEWAY_PORT}/v1/rtc/calls" "rtc fixture route" 30 || { echo "gateway log: $GATEWAY_LOG" >&2; exit 1; }

python3 - "$REPORT" "$MANIFEST" "$GATEWAY_BASE_URL" "$ASSISTANT_PORT" "$DEVICE_KIND" "$LOCAL_PUBLIC_HOST" "$MEDIA_AVATAR_CDN_BASE_URL" "$MEDIA_IMAGE_CDN_BASE_URL" "$MEDIA_VIDEO_CDN_BASE_URL" "$MEDIA_UPLOAD_BASE_URL" "$ADB_REVERSE_ENABLED" <<'PY'
import json
import sys
from pathlib import Path

(
    report_path,
    manifest_path,
    gateway,
    assistant_port,
    device_kind,
    local_public_host,
    avatar_cdn,
    image_cdn,
    video_cdn,
    upload_base,
    adb_reverse,
) = sys.argv[1:12]
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
report = {
    "status": "ready",
    "mode": "manual-beta",
    "appRuntimeEnv": "beta",
    "appDataSource": "remote",
    "gatewayBaseUrl": gateway,
    "deviceKind": device_kind,
    "localPublicHost": local_public_host,
    "avatarCdnBaseUrl": avatar_cdn,
    "imageCdnBaseUrl": image_cdn,
    "videoCdnBaseUrl": video_cdn,
    "uploadBaseUrl": upload_base,
    "adbReverseEnabled": adb_reverse == "1",
    "assistantServiceUrl": f"http://127.0.0.1:{assistant_port}",
    "manifest": str(Path(manifest_path)),
    "checkedRoutes": [
        "/healthz",
        "/v1/assistant/skill-subscriptions",
        "/v1/config/app",
        "/v1/content/feed",
        "/v1/chat/inbox",
        "/v1/chat/contacts",
        "/v1/chat/conversations",
        "/v1/circles",
        "/v1/circles/fixture_circle_photo/feed",
        "/v1/user/profile",
        "/v1/me",
        "/v1/user/personas/active",
        "/v1/user/settings/appearance",
        "/v1/content/profile-subjects/fixture_user_current/posts",
        "/v1/users/fixture_user_current/works",
        "/v1/users/fixture_user_current/circles",
        "/v1/user/profile-subjects/fixture_user_current/relationship/capability",
        "/v1/entity/homepages",
        "/v1/integration/locations/pois",
        "/v1/app-messages",
        "/v1/rtc/calls",
    ],
    "checkedMediaUrls": [
        f"{avatar_cdn.rstrip('/')}/media/avatar/beta-avatar.png",
        f"{image_cdn.rstrip('/')}/media/image/beta-cover.png",
        f"{video_cdn.rstrip('/')}/media/video/beta-sample.mp4",
    ],
    "seedRefs": {
        item["domain"]: item["refs"]
        for item in manifest.get("seedRefs", [])
    },
}
Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "[app-beta-manual] beta environment is ready."
echo "[app-beta-manual] report: $REPORT"
echo "[app-beta-manual] APP_RUNTIME_ENV=beta APP_DATA_SOURCE=remote CLOUD_GATEWAY_BASE_URL=$GATEWAY_BASE_URL APP_CURRENT_USER_ID=$APP_CURRENT_USER_ID"

if [[ "$SKIP_APP" == "1" ]]; then
  echo "[app-beta-manual] --skip-app set; beta cloud stack keeps running until Ctrl-C."
  beta_manual_wait_until_stopped assistant-service gateway media-static
  exit 0
fi

flutter_args=(
  run
  --dart-define=APP_RUNTIME_ENV=beta
  --dart-define=APP_DATA_SOURCE=remote
  "--dart-define=APP_CURRENT_USER_ID=${APP_CURRENT_USER_ID}"
  "--dart-define=CLOUD_GATEWAY_BASE_URL=${GATEWAY_BASE_URL}"
  "--dart-define=MEDIA_AVATAR_CDN_BASE_URL=${MEDIA_AVATAR_CDN_BASE_URL}"
  "--dart-define=MEDIA_IMAGE_CDN_BASE_URL=${MEDIA_IMAGE_CDN_BASE_URL}"
  "--dart-define=MEDIA_VIDEO_CDN_BASE_URL=${MEDIA_VIDEO_CDN_BASE_URL}"
  "--dart-define=MEDIA_UPLOAD_BASE_URL=${MEDIA_UPLOAD_BASE_URL}"
)
if [[ -n "$FLUTTER_DEVICE_ID" ]]; then
  flutter_args+=(-d "$FLUTTER_DEVICE_ID")
fi

echo "[app-beta-manual] starting Flutter app..."
cd "$APP_DIR"
flutter "${flutter_args[@]}"
