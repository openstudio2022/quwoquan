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
bash "$ROOT_DIR/agent_ops/deploy/alpha/start_alpha_mock_stack.sh" up
