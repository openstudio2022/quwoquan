#!/usr/bin/env bash
set -euo pipefail

# Flutter's iOS build path does not run quwoquan_app/run.sh. Keep bare
# `flutter run -d <ios-simulator>` on the same alpha HTTPS contract by preparing
# the local public plane from Xcode's Debug/Profile build phase.

if [[ "${QWQ_IOS_LOCAL_AUTO_PREPARE:-1}" == "0" ]]; then
  echo "[ios-alpha-local] skipped by QWQ_IOS_LOCAL_AUTO_PREPARE=0"
  exit 0
fi

case "${CONFIGURATION:-Debug}" in
  Debug|Profile) ;;
  *)
    exit 0
    ;;
esac

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"

RUNTIME_ENV="$(
  python3 - <<'PY'
import base64
import os

defines = os.environ.get("DART_DEFINES", "").strip()
for item in filter(None, defines.split(",")):
    try:
        decoded = base64.b64decode(item).decode("utf-8", errors="replace")
    except Exception:
        continue
    if decoded.startswith("APP_RUNTIME_ENV="):
        print(decoded.split("=", 1)[1].strip())
        break
PY
)"

# No APP_RUNTIME_ENV means Flutter's local debug default applies; this repo's
# supported bare flutter-run default is alpha.
if [[ -n "$RUNTIME_ENV" && "$RUNTIME_ENV" != "alpha" ]]; then
  echo "[ios-alpha-local] skipped for APP_RUNTIME_ENV=$RUNTIME_ENV"
  exit 0
fi

echo "[ios-alpha-local] preparing alpha HTTPS public plane for flutter run"
# CI/Patrol 会提供明确的 Simulator UDID；Xcode build phase 若暴露
# TARGET_DEVICE_IDENTIFIER，只将其作为设备专属传递，绝不回退到任意 booted Simulator。
if [[ -z "${QWQ_IOS_SIMULATOR_UDID:-}" && -n "${TARGET_DEVICE_IDENTIFIER:-}" ]]; then
  export QWQ_IOS_SIMULATOR_UDID="$TARGET_DEVICE_IDENTIFIER"
fi
if [[ "${EFFECTIVE_PLATFORM_NAME:-}" == *"iphonesimulator"* || "${PLATFORM_NAME:-}" == "iphonesimulator" ]]; then
  if [[ -z "${QWQ_IOS_SIMULATOR_UDID:-}" ]]; then
    echo "[ios-alpha-local] GATE_BLOCK: Simulator CA trust needs TARGET_DEVICE_IDENTIFIER or QWQ_IOS_SIMULATOR_UDID." >&2
    echo "[ios-alpha-local] Repair: run flutter with an explicit Simulator device, then rerun the build." >&2
    exit 2
  fi
  export QWQ_IOS_SIMULATOR_CA_REQUIRED=1
fi
# iOS Simulator validates HTTPS against the booted simulator keychain, not the
# macOS login keychain. Skip macOS trustRoot writes here to avoid the repeated
# Certificate Trust Settings password prompt on every flutter run build.
QWQ_ALPHA_LOCAL_MACOS_KEYCHAIN_TRUST=skip \
  bash "$ROOT_DIR/quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh" up
