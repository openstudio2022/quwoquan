#!/usr/bin/env bash
set -euo pipefail

# Xcode 直接构建不会经过 `flutter run --dart-define=...`。这里从同一环境包生成
# 端点定义，再与 Flutter 自身的版本定义合并，禁止静默产出缺端点安装包。

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_NAME="${QWQ_APP_RUNTIME_ENV:-alpha}"

case "$ENV_NAME" in
  alpha|beta|gamma|prod) ;;
  *)
    echo "[ios-dart-defines] FAIL: QWQ_APP_RUNTIME_ENV must be alpha|beta|gamma|prod." >&2
    exit 2
    ;;
esac

RUNTIME_DEFINES_JSON="$(
  python3 "$APP_DIR/scripts/env/print_app_env_dart_defines.py" \
    --env "$ENV_NAME" \
    --format json
)"

python3 - "$RUNTIME_DEFINES_JSON" "${DART_DEFINES:-}" <<'PY'
import base64
import json
import shlex
import sys

runtime_defines = json.loads(sys.argv[1])
existing = sys.argv[2].strip()

merged = {}
for encoded in filter(None, existing.split(",")):
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        continue
    if "=" not in decoded:
        continue
    key, value = decoded.split("=", 1)
    merged[key] = value

merged.update(runtime_defines)
encoded_defines = [
    base64.b64encode(f"{key}={value}".encode("utf-8")).decode("ascii")
    for key, value in sorted(merged.items())
]
print("export DART_DEFINES=" + shlex.quote(",".join(encoded_defines)))
print("export QWQ_IOS_DART_DEFINES_READY=1")
PY
