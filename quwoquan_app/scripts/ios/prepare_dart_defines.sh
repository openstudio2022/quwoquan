#!/usr/bin/env bash
set -euo pipefail

# Xcode 直接构建不会经过 `flutter run --dart-define=...`。这里从同一环境包生成
# 端点定义，再与 Flutter 自身的版本定义合并，禁止静默产出缺端点安装包。

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXISTING_RUNTIME_ENV="$(
  python3 - "${DART_DEFINES:-}" <<'PY'
import base64
import sys

for encoded in filter(None, sys.argv[1].strip().split(",")):
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        continue
    if decoded.startswith("APP_RUNTIME_ENV="):
        print(decoded.split("=", 1)[1].strip())
        break
PY
)"
ENV_NAME="${QWQ_APP_RUNTIME_ENV:-${EXISTING_RUNTIME_ENV:-}}"
LAUNCH_MODE="${QWQ_APP_LAUNCH_MODE:-xcode_build}"

if [[ -z "$ENV_NAME" ]]; then
  echo "[ios-dart-defines] FAIL: explicit QWQ_APP_RUNTIME_ENV or DART_DEFINES APP_RUNTIME_ENV is required." >&2
  exit 2
fi

if [[ -n "${QWQ_APP_RUNTIME_ENV:-}" \
   && -n "$EXISTING_RUNTIME_ENV" \
   && "$QWQ_APP_RUNTIME_ENV" != "$EXISTING_RUNTIME_ENV" ]]; then
  echo "[ios-dart-defines] FAIL: QWQ_APP_RUNTIME_ENV=$QWQ_APP_RUNTIME_ENV conflicts with DART_DEFINES APP_RUNTIME_ENV=$EXISTING_RUNTIME_ENV." >&2
  exit 2
fi

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
    --format json \
    --launch-mode "$LAUNCH_MODE"
)"

python3 - "$RUNTIME_DEFINES_JSON" "${DART_DEFINES:-}" <<'PY'
import base64
import json
import shlex
import sys
from urllib.parse import urlparse

runtime_defines = json.loads(sys.argv[1])
existing = sys.argv[2].strip()
expected_env = runtime_defines.get("APP_RUNTIME_ENV", "")
required_keys = {
    "APP_RUNTIME_ENV",
    "CLOUD_GATEWAY_BASE_URL",
    "APP_LEGAL_BASE_URL",
    "MEDIA_AVATAR_CDN_BASE_URL",
    "MEDIA_IMAGE_CDN_BASE_URL",
    "MEDIA_VIDEO_CDN_BASE_URL",
    "MEDIA_UPLOAD_BASE_URL",
    "RTC_MEDIA_CONNECTION_URL",
}
device_local_transport_keys = {
    "CLOUD_GATEWAY_BASE_URL",
    "MEDIA_AVATAR_CDN_BASE_URL",
    "MEDIA_IMAGE_CDN_BASE_URL",
    "MEDIA_VIDEO_CDN_BASE_URL",
    "MEDIA_UPLOAD_BASE_URL",
}


def is_authorized_local_transport(raw: str, canonical: str) -> bool:
    candidate = urlparse(raw.strip())
    expected = urlparse(canonical.strip())
    if not (
        candidate.scheme == expected.scheme == "https"
        and candidate.port == expected.port
        and candidate.path == expected.path
        and candidate.params == expected.params
        and candidate.query == expected.query
        and candidate.fragment == expected.fragment
    ):
        return False
    candidate_host = (candidate.hostname or "").lower()
    expected_host = (expected.hostname or "").lower()
    if candidate_host == "localhost":
        return True
    public_suffix = ".quwoquan-env.test"
    if not expected_host.endswith(public_suffix):
        return False
    local_host = expected_host[: -len(public_suffix)] + ".localhost"
    return candidate_host == local_host

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

for key, value in runtime_defines.items():
    supplied = merged.get(key, "")
    if (
        key in device_local_transport_keys
        and is_authorized_local_transport(supplied, value)
    ):
        continue
    merged[key] = value
missing = sorted(key for key in required_keys if not merged.get(key, "").strip())
if missing:
    print(
        "[ios-dart-defines] FAIL: incomplete runtime package; missing "
        + ", ".join(missing),
        file=sys.stderr,
    )
    raise SystemExit(3)
if not expected_env or merged["APP_RUNTIME_ENV"] != expected_env:
    print(
        "[ios-dart-defines] FAIL: APP_RUNTIME_ENV does not match selected package.",
        file=sys.stderr,
    )
    raise SystemExit(4)

encoded_defines = [
    base64.b64encode(f"{key}={value}".encode("utf-8")).decode("ascii")
    for key, value in sorted(merged.items())
]
print(
    "[ios-dart-defines] env="
    + expected_env
    + " verifiedKeys="
    + ",".join(sorted(required_keys)),
    file=sys.stderr,
)
print("export DART_DEFINES=" + shlex.quote(",".join(encoded_defines)))
print("export QWQ_IOS_DART_DEFINES_READY=1")
PY
