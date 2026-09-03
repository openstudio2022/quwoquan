#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
ENVIRONMENT="${QWQ_ENVIRONMENT:-alpha}"
DEVICE_ID=""
RUN_MODE="${QWQ_RUN_MODE:-content-live}"
VERBOSE=""
log() { printf '[dev] %s\n' "$*" >&2; }
block() { printf '[dev] GATE_BLOCK: %s\n' "$*" >&2; exit 2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) [[ -n "${2:-}" ]] || block "--env requires alpha|beta|gamma"; ENVIRONMENT="$2"; shift 2 ;;
    --env=*) ENVIRONMENT="${1#*=}"; shift ;;
    --target) [[ -n "${2:-}" ]] || block "--target requires <env>-local"; ENVIRONMENT="${2%-local}"; shift 2 ;;
    --target=*) ENVIRONMENT="${1#*=}"; ENVIRONMENT="${ENVIRONMENT%-local}"; shift ;;
    -d|--device|--device-id)
      [[ -n "${2:-}" ]] || block "$1 requires a device id"
      [[ -z "$DEVICE_ID" || "$DEVICE_ID" == "$2" ]] || block "conflicting device selectors are forbidden"
      DEVICE_ID="$2"; shift 2 ;;
    --device=*|--device-id=*)
      value="${1#*=}"; [[ -z "$DEVICE_ID" || "$DEVICE_ID" == "$value" ]] || block "conflicting device selectors are forbidden"
      DEVICE_ID="$value"; shift ;;
    --mode) [[ -n "${2:-}" ]] || block "--mode requires content-live|ui-only"; RUN_MODE="$2"; shift 2 ;;
    --mode=*) RUN_MODE="${1#*=}"; shift ;;
    -v|--verbose) VERBOSE=--verbose; shift ;;
    -h|--help)
      echo "Usage: run.sh [--env alpha|beta|gamma] [--mode content-live|ui-only] [-d <device>] [-v]" >&2
      echo "       run.sh --hermetic ...   走发布级流水线（源码冻结 + 依赖胶囊 + lease）" >&2
      exit 0 ;;
    *) block "APP.LAUNCH.managed_argument_unsupported: $1（开发直连只接受 --env/--target/-d/--mode/-v；其余参数请用 run.sh --hermetic）" ;;
  esac
done
case "$ENVIRONMENT" in alpha|beta|gamma) ;; *) block "--env must be alpha|beta|gamma (got '$ENVIRONMENT')" ;; esac
case "$RUN_MODE" in content-live|ui-only) ;; *) block "--mode must be content-live|ui-only (got '$RUN_MODE')" ;; esac
python3 - "${QWQ_APP_ACTIVATION_TIMEOUT_SECONDS:-30}" "${QWQ_APP_LAUNCH_TIMEOUT_SECONDS:-900}" <<'PY' || block "activation and launch timeouts must be positive finite numbers"
import math, sys
if any(not math.isfinite(float(value)) or float(value) <= 0 for value in sys.argv[1:]): raise SystemExit(2)
PY

PREFLIGHT_PURPOSE="$(python3 - "$RUN_MODE" <<'PY'
import sys
from quwoquan_ops.cli.lib.app_debug_preflight_handoff import (
    app_debug_preflight_purpose,
)

try:
    print(app_debug_preflight_purpose(sys.argv[1]))
except ValueError as error:
    print(error, file=sys.stderr)
    raise SystemExit(2) from None
PY
)" || block "invalid App launch preflight purpose"
PREFLIGHT_STATUS=0
if APP_DEBUG_PREFLIGHT_JSON="$(
  python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
    app-debug-preflight --purpose "$PREFLIGHT_PURPOSE" \
    --target "${ENVIRONMENT}-local" --runtime-mode test_live
)"; then
  :
else
  PREFLIGHT_STATUS=$?
  [[ -z "$APP_DEBUG_PREFLIGHT_JSON" ]] || printf '%s\n' "$APP_DEBUG_PREFLIGHT_JSON" >&2
  # stackctl owns the typed blocker and normally returns 2. Preserve any
  # other non-zero status so launcher transport failures are not relabeled.
  exit "$PREFLIGHT_STATUS"
fi
PREFLIGHT_WARNING_TEXT="$(python3 - \
  "$APP_DEBUG_PREFLIGHT_JSON" "$PREFLIGHT_PURPOSE" "${ENVIRONMENT}-local" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except (TypeError, ValueError):
    raise SystemExit("App debug preflight output is not JSON") from None
if not isinstance(payload, dict):
    raise SystemExit("App debug preflight output is not an object")
required_fields = {
    "exitCode",
    "status",
    "purpose",
    "nonPromotable",
    "firstBlocker",
    "target",
    "environment",
    "details",
    "warnings",
}
if not required_fields.issubset(payload):
    raise SystemExit("App debug preflight output is incomplete")
if (
    type(payload.get("exitCode")) is not int
    or payload.get("exitCode") != 0
    or payload.get("status") not in {"passed", "warning"}
    or payload.get("purpose") != sys.argv[2]
    or payload.get("nonPromotable") is not True
    or str(payload.get("firstBlocker") or "").strip()
    or payload.get("target") != sys.argv[3]
    or payload.get("environment") != sys.argv[3].removesuffix("-local")
    or not isinstance(payload.get("details"), list)
    or not isinstance(payload.get("warnings"), list)
    or not all(isinstance(item, str) for item in payload["warnings"])
):
    raise SystemExit("App debug preflight did not return launchable test_live readiness")
for warning in payload.get("warnings") or []:
    print(str(warning).replace("\n", " "))
PY
)" || block "App debug preflight contract is invalid"
while IFS= read -r preflight_warning; do
  [[ -n "$preflight_warning" ]] || continue
  log "WARN: $preflight_warning"
done <<< "$PREFLIGHT_WARNING_TEXT"
# Workspace-direct test_live intentionally carries no release-grade consumer
# lease. Keep that absence visible and non-promotable without blocking compile.
log "WARN: runtime consumer lease is unavailable; test_live remains nonPromotable."

log "tree: $APP_DIR"
if ! SDK_JSON="$(python3 "$APP_DIR/scripts/tools/flutter_facade/resolve_real_flutter.py" --format json)"; then
  block "APP.LAUNCH.workspace_flutter_sdk_unavailable: 真实 Flutter SDK 解析失败（见上方输出）"
fi
REAL_FLUTTER="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["executable"])' "$SDK_JSON")"
export QWQ_REAL_FLUTTER="$REAL_FLUTTER"
log "sdk: $REAL_FLUTTER; device: discovering (flutter devices --machine)…"
# 脚本经 -c 传入而非 stdin heredoc：多设备时 pick_device 需要 stdin/stderr 都是 TTY
# 才能给出编号选择；heredoc 会占用 stdin，使交互终端也被判为非 TTY 而必然阻断。
DEVICE_SELECT_SCRIPT="$(cat <<'PY'
import shlex, sys
from pathlib import Path
from quwoquan_ops.cli.lib.dev_up import discover_flutter_devices, select_device

app_dir, real_flutter, requested = sys.argv[1:4]
try:
    devices = discover_flutter_devices(
        Path(app_dir), include_web=False, include_desktop=False, flutter_executable=real_flutter
    )
    device_id = select_device(devices, device_id=requested, label="[dev]")
except (OSError, RuntimeError, ValueError) as error:
    message = str(error)
    print(message if message.startswith("GATE_BLOCK:") else f"GATE_BLOCK: {message}", file=sys.stderr)
    raise SystemExit(2)
device = next(item for item in devices if item["id"] == device_id)
target, emulator = device["targetPlatform"].lower(), bool(device["emulator"])
if target == "ios":
    kind, platform = ("ios-simulator" if emulator else "ios-physical"), "ios"
elif target.startswith("android"):
    kind, platform = ("android_emulator" if emulator else "android_physical"), "android"
else:
    print(f"GATE_BLOCK: unsupported device platform {target!r}", file=sys.stderr)
    raise SystemExit(2)
print("DEVICE_ID=" + shlex.quote(device_id))
print("DEVICE_KIND=" + shlex.quote(kind))
print("PLATFORM=" + shlex.quote(platform))
print("DEVICE_NAME=" + shlex.quote(device["name"]))
PY
)"
DEVICE_EXPORTS="$(python3 -c "$DEVICE_SELECT_SCRIPT" "$APP_DIR" "$REAL_FLUTTER" "$DEVICE_ID")" || exit 2
eval "$DEVICE_EXPORTS"
log "device: $DEVICE_NAME ($DEVICE_ID, $DEVICE_KIND)"
if [[ "$PLATFORM" == "ios" && -z "${QWQ_COCOAPODS_BINDING_SEAL:-}" ]]; then
  COCOAPODS_EXPORTS="$(python3 - <<'PY'
import shlex, sys
from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    AppDependencyToolchainError, resolve_cocoapods_identity,
)
try:
    identity = resolve_cocoapods_identity()
except AppDependencyToolchainError as error:
    print(f"GATE_BLOCK: {error}", file=sys.stderr)
    raise SystemExit(2)
for key, value in identity.as_environment().items():
    print(f"export {key}={shlex.quote(value)}")
PY
)" || exit 2
  eval "$COCOAPODS_EXPORTS"
fi
PACKAGE_CONFIG="$APP_DIR/.dart_tool/package_config.json"
PACKAGE_STAMP="$APP_DIR/.dart_tool/qwq_dev_pub_inputs.sha256"
PUB_INPUT_DIGEST="$(shasum -a 256 "$APP_DIR/pubspec.yaml" "$APP_DIR/pubspec.lock" | shasum -a 256 | awk '{print $1}')"
if [[ ! -f "$PACKAGE_CONFIG" || ! -f "$PACKAGE_STAMP" || "$(<"$PACKAGE_STAMP")" != "$PUB_INPUT_DIGEST" ]]; then
  log "deps: pubspec changed → flutter pub get（本机 PUB_CACHE）"
  (cd "$APP_DIR" && "$REAL_FLUTTER" pub get) || block "flutter pub get failed（见上方输出）"
  mkdir -p "$(dirname "$PACKAGE_STAMP")"
  printf '%s\n' "$PUB_INPUT_DIGEST" > "$PACKAGE_STAMP"
else
  log "deps: pub inputs unchanged; pub get skipped（iOS Pods 由 flutter build 按需安装）"
fi
MATERIAL_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/qwq-dev-launch.XXXXXX")"
mkdir -m 0700 "$MATERIAL_ROOT/qwq_runtime"
trap 'rm -rf -- "$MATERIAL_ROOT"' EXIT
TRUST_PATH="$MATERIAL_ROOT/qwq_runtime/runtime-config-trust.json"
log "config: signing $ENVIRONMENT runtime package + trust envelope (test_live)"
if ! HANDOFF_JSON="$(python3 "$APP_DIR/scripts/device/build_launcher_handoff.py" \
    --env "$ENVIRONMENT" --target "${ENVIRONMENT}-local" \
    --launch-provenance canonical_launcher --launch-policy test_live \
    --runtime-config-trust-output "$TRUST_PATH")"; then
  [[ -z "$HANDOFF_JSON" ]] || echo "$HANDOFF_JSON" >&2
  block "launcher handoff generation failed"
fi
ENTRYPOINT="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["entrypoint"])' "$HANDOFF_JSON")"
APP_ID="$(python3 -c 'import sys
from quwoquan_ops.cli.lib.app_identity import resolve_app_identity
print(resolve_app_identity(platform=sys.argv[1], build_profile="nonprod", build_mode="debug").application_id)' "$PLATFORM")"
if [[ "$DEVICE_KIND" == "ios-simulator" ]]; then
  DATA_ROOT="$(xcrun simctl get_app_container "$DEVICE_ID" "$APP_ID" data 2>/dev/null || true)"
  LEGACY_RECEIPT="$DATA_ROOT/Library/Application Support/qwq_runtime/runtime-config-active-receipt.json"
  if [[ -f "$LEGACY_RECEIPT" ]] && grep -q '"runtimeConfigSupplyMode":"embedded_default_package"' "$LEGACY_RECEIPT"; then
    rm -f "${LEGACY_RECEIPT%/*}"/runtime-config-*.json
  fi
elif [[ "$PLATFORM" == "android" ]] && adb -s "$DEVICE_ID" shell run-as "$APP_ID" sh -c "'grep -q embedded_default_package no_backup/runtime-config-active-receipt.json'" 2>/dev/null; then
  adb -s "$DEVICE_ID" shell run-as "$APP_ID" sh -c "'rm -f no_backup/runtime-config-*.json'"
fi
export QWQ_ENVIRONMENT="$ENVIRONMENT" QWQ_APP_RUNTIME_ENV="$ENVIRONMENT"
export QWQ_LAUNCH_TARGET="${ENVIRONMENT}-local" QWQ_APP_RUN_MODE="$RUN_MODE"
export QWQ_APP_BUILD_PROFILE=nonprod QWQ_APP_BUILD_CONTEXT=runtime QWQ_APP_LAUNCH_POLICY=test_live
export QWQ_APP_LAUNCH_PROVENANCE=canonical_launcher QWQ_LAUNCH_HANDOFF_JSON="$HANDOFF_JSON"
export QWQ_APP_RUNTIME_CONFIG_TRUST_PATH="$TRUST_PATH" QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH="$TRUST_PATH"
export QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT="$MATERIAL_ROOT"
unset QWQ_MANAGED_FLUTTER_ENTRY
log "launch: $APP_ID on $DEVICE_ID → build / install / activate / attach（r 热重载 R 热重启 q 退出）"
EXIT_CODE=0
python3 "$APP_DIR/scripts/device/run_app_instance.py" \
  --device-kind "$DEVICE_KIND" --device "$DEVICE_ID" \
  --application-id "$APP_ID" --entrypoint "$ENTRYPOINT" \
  --activation-timeout-seconds "${QWQ_APP_ACTIVATION_TIMEOUT_SECONDS:-30}" \
  --attach-timeout-seconds "${QWQ_APP_LAUNCH_TIMEOUT_SECONDS:-900}" \
  -- ${VERBOSE:+"$VERBOSE"} || EXIT_CODE=$?
[[ "$EXIT_CODE" == "0" ]] || log "launch ended with exit code $EXIT_CODE"
exit "$EXIT_CODE"
