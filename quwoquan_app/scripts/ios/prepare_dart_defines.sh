#!/usr/bin/env bash
set -euo pipefail

# Xcode phase 只验证 canonical launcher 传入的同一份 handoff。
# 裸 `flutter run` 无法保证 resident compiler 在 Hot Restart 时保留 defines，
# 因此必须在安装前失败，禁止 Xcode 临时合成第二份配置。

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
EXISTING_LAUNCH_MODE="$(
  python3 - "${DART_DEFINES:-}" <<'PY'
import base64
import sys

for encoded in filter(None, sys.argv[1].strip().split(",")):
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        continue
    if decoded.startswith("QWQ_APP_LAUNCH_MODE="):
        print(decoded.split("=", 1)[1].strip())
        break
PY
)"
ENV_NAME="${QWQ_APP_RUNTIME_ENV:-${EXISTING_RUNTIME_ENV:-}}"
LAUNCH_MODE="${QWQ_APP_LAUNCH_MODE:-${EXISTING_LAUNCH_MODE:-}}"

if [[ -z "$ENV_NAME" ]]; then
  echo "[ios-dart-defines] GATE_BLOCK: canonical runtime handoff is required; use ./run.sh -d <device>." >&2
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

if [[ -z "$LAUNCH_MODE" ]]; then
  echo "[ios-dart-defines] GATE_BLOCK: canonical launch mode is required; use ./run.sh -d <device>." >&2
  exit 2
fi

RUNTIME_DEFINES_JSON="$(
  python3 "$APP_DIR/scripts/env/print_app_env_dart_defines.py" \
    --env "$ENV_NAME" \
    --format json \
    --launch-mode "$LAUNCH_MODE"
)"

python3 - \
  "$RUNTIME_DEFINES_JSON" \
  "${DART_DEFINES:-}" <<'PY'
import base64
import json
import os
import shlex
import sys

runtime_defines = json.loads(sys.argv[1])
existing = sys.argv[2].strip()
expected_env = runtime_defines.get("APP_RUNTIME_ENV", "")
launch_target = os.environ.get("QWQ_LAUNCH_TARGET", "").strip()
effective_manifest_digest = os.environ.get(
    "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
    "",
).strip()
dart_defines_digest = os.environ.get("QWQ_DART_DEFINES_DIGEST", "").strip()
runtime_config_digest = os.environ.get(
    "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
    "",
).strip()
if not launch_target:
    print(
        "[ios-dart-defines] FAIL: canonical QWQ_LAUNCH_TARGET is required.",
        file=sys.stderr,
    )
    raise SystemExit(5)
for label, value in (
    ("QWQ_DART_DEFINES_DIGEST", dart_defines_digest),
    ("QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST", runtime_config_digest),
    ("QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST", effective_manifest_digest),
):
    if not value.startswith("sha256:") or len(value) != 71:
        print(
            f"[ios-dart-defines] FAIL: canonical {label} is required.",
            file=sys.stderr,
        )
        raise SystemExit(5)
required_keys = {
    "APP_RUNTIME_ENV",
    "CLOUD_GATEWAY_BASE_URL",
    "APP_LEGAL_BASE_URL",
    "PUBLIC_WEB_BASE_URL",
    "APP_DOWNLOAD_BASE_URL",
    "REALTIME_CONNECTION_URL",
    "MEDIA_AVATAR_CDN_BASE_URL",
    "MEDIA_IMAGE_CDN_BASE_URL",
    "MEDIA_VIDEO_CDN_BASE_URL",
    "MEDIA_UPLOAD_BASE_URL",
    "RTC_MEDIA_CONNECTION_URL",
}

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

target_build_dir = os.environ.get("TARGET_BUILD_DIR", "").strip()
resources_folder = os.environ.get(
    "UNLOCALIZED_RESOURCES_FOLDER_PATH",
    "",
).strip()
if target_build_dir and resources_folder:
    import plistlib
    from pathlib import Path

    resource_root = Path(target_build_dir) / resources_folder
    resource_root.mkdir(parents=True, exist_ok=True)
    manifest_path = resource_root / "QWQNativeRuntime.plist"
    temporary_path = manifest_path.with_suffix(".plist.tmp")
    with temporary_path.open("wb") as stream:
        plistlib.dump(
            {
                "runtimeEnvironment": merged["APP_RUNTIME_ENV"],
                "runtimeConfigDigest": runtime_config_digest,
                "dartDefinesDigest": dart_defines_digest,
                "effectiveLaunchManifestDigest": effective_manifest_digest,
                "launchTarget": launch_target,
                "entrypoint": "lib/main_prod.dart",
                "launchMode": runtime_defines.get("QWQ_APP_LAUNCH_MODE", ""),
                "recoveryBaseURL": merged["CLOUD_GATEWAY_BASE_URL"],
                "publicWebURL": merged["PUBLIC_WEB_BASE_URL"],
                "appDownloadBaseURL": merged["APP_DOWNLOAD_BASE_URL"],
            },
            stream,
            sort_keys=True,
        )
    temporary_path.replace(manifest_path)

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
