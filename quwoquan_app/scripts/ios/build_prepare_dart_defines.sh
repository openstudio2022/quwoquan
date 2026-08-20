#!/usr/bin/env bash
set -euo pipefail

# Xcode phase 优先验证 canonical launcher 传入的同一份 handoff。
# 裸 `flutter run` 的 Debug 构建没有 shell wrapper，因此只允许在完全没有显式
# identity 时从 metadata 生成 canonical Alpha/Beta/Gamma handoff；Hot Restart 由 native manifest
# 回灌同一 runtime package，禁止在 App 代码中复制 endpoint。

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACKCTL_PYTHON_RESOLVER="$APP_DIR/scripts/ios/build_resolve_stackctl_python.sh"
RUNTIME_PYTHON="$(bash "$STACKCTL_PYTHON_RESOLVER")" || {
  echo "[ios-dart-defines] GATE_BLOCK: build requires Python 3.10+ with PyYAML." >&2
  exit 2
}
EXISTING_RUNTIME_ENV="$(
  "$RUNTIME_PYTHON" - "${DART_DEFINES:-}" <<'PY'
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
  "$RUNTIME_PYTHON" - "${DART_DEFINES:-}" <<'PY'
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
EXISTING_LAUNCH_POLICY="$(
  "$RUNTIME_PYTHON" - "${DART_DEFINES:-}" <<'PY'
import base64
import sys

for encoded in filter(None, sys.argv[1].strip().split(",")):
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        continue
    if decoded.startswith("APP_LAUNCH_POLICY="):
        print(decoded.split("=", 1)[1].strip())
        break
PY
)"
ENV_NAME="${QWQ_APP_RUNTIME_ENV:-${EXISTING_RUNTIME_ENV:-}}"
LAUNCH_MODE="${QWQ_APP_LAUNCH_MODE:-${EXISTING_LAUNCH_MODE:-}}"
DIRECT_RUNTIME_DEFINES_JSON=""
if [[ -n "${QWQ_LAUNCH_HANDOFF_JSON:-}" ]]; then
  CANONICAL_HANDOFF_EXPORTS="$(
    PYTHONDONTWRITEBYTECODE=1 "$RUNTIME_PYTHON" - \
      "$QWQ_LAUNCH_HANDOFF_JSON" "${DART_DEFINES:-}" "$APP_DIR" <<'PY'
import base64
import json
import os
import shlex
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise ValueError(message)


try:
    handoff = json.loads(sys.argv[1])
except (IndexError, json.JSONDecodeError) as exc:
    fail(f"canonical launcher handoff is not valid JSON: {exc}")
if not isinstance(handoff, dict) or handoff.get("schema") != "app-launcher-handoff":
    fail("canonical launcher handoff schema is invalid")
sys.path.insert(0, str(Path(sys.argv[3]) / "scripts/device"))
from launch_manifest_metadata import (  # noqa: E402
    load_launch_manifest_contract,
    validate_handoff_against_metadata,
)

contract_issues = validate_handoff_against_metadata(
    handoff,
    load_launch_manifest_contract(),
)
if contract_issues:
    fail("; ".join(contract_issues))
effective = handoff.get("effectiveLaunchManifest")
if not isinstance(effective, dict) or effective.get("schema") != (
    "app-effective-launch-manifest"
):
    fail("canonical effective launch manifest is invalid")
for field, value in effective.items():
    if field != "schema" and handoff.get(field) != value:
        fail(f"launcher handoff/effective manifest mismatch: {field}")

defines = handoff.get("dartDefines")
if not isinstance(defines, dict) or any(
    not isinstance(key, str) or not isinstance(value, str)
    for key, value in defines.items()
):
    fail("canonical launcher handoff Dart defines are invalid")
required_define_keys = {
    "APP_RUNTIME_ENV",
    "QWQ_APP_LAUNCH_MODE",
    "APP_LAUNCH_POLICY",
    "CLOUD_GATEWAY_BASE_URL",
    "PUBLIC_WEB_BASE_URL",
    "APP_DOWNLOAD_BASE_URL",
}
missing = sorted(required_define_keys - defines.keys())
if missing:
    fail("canonical launcher handoff Dart defines are incomplete: " + ", ".join(missing))
expected_define_values = {
    "APP_RUNTIME_ENV": str(handoff.get("environment") or ""),
    "QWQ_APP_LAUNCH_MODE": str(handoff.get("launchMode") or ""),
    "APP_LAUNCH_POLICY": str(handoff.get("launchPolicy") or ""),
    "CLOUD_GATEWAY_BASE_URL": str(handoff.get("recoveryBaseUrl") or ""),
    "PUBLIC_WEB_BASE_URL": str(handoff.get("publicWebBaseUrl") or ""),
    "APP_DOWNLOAD_BASE_URL": str(handoff.get("appDownloadBaseUrl") or ""),
}
mismatched_defines = sorted(
    key for key, value in expected_define_values.items() if defines.get(key) != value
)
if mismatched_defines:
    fail(
        "canonical launcher handoff Dart define projection mismatch: "
        + ", ".join(mismatched_defines)
    )

digest_fields = {
    "QWQ_DART_DEFINES_DIGEST": "dartDefinesDigest",
    "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST": "runtimeConfigDigest",
    "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": "effectiveLaunchManifestDigest",
}
for environment_key, handoff_key in digest_fields.items():
    value = str(handoff.get(handoff_key) or "")
    if not value.startswith("sha256:") or len(value) != 71:
        fail(f"canonical launcher handoff {handoff_key} is invalid")

identity_fields = {
    "QWQ_APP_RUNTIME_ENV": "environment",
    "QWQ_LAUNCH_TARGET": "target",
    "QWQ_APP_LAUNCH_MODE": "launchMode",
    "QWQ_APP_LAUNCH_POLICY": "launchPolicy",
    **digest_fields,
}
for environment_key, handoff_key in identity_fields.items():
    supplied = os.environ.get(environment_key, "").strip()
    expected = str(handoff.get(handoff_key) or "")
    if supplied and supplied != expected:
        fail(f"{environment_key} conflicts with canonical launcher handoff")

existing_defines: dict[str, str] = {}
for encoded in filter(None, sys.argv[2].strip().split(",")):
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        continue
    if "=" not in decoded:
        continue
    key, value = decoded.split("=", 1)
    existing_defines[key] = value
conflicting_existing = sorted(
    key
    for key, value in existing_defines.items()
    if key in defines and value != defines[key]
)
if conflicting_existing:
    fail(
        "DART_DEFINES conflict with canonical launcher handoff: "
        + ", ".join(conflicting_existing)
    )

exports = {
    "QWQ_APP_RUNTIME_ENV": handoff["environment"],
    "QWQ_LAUNCH_TARGET": handoff["target"],
    "QWQ_APP_LAUNCH_MODE": handoff["launchMode"],
    "QWQ_APP_LAUNCH_POLICY": handoff["launchPolicy"],
    **{
        environment_key: handoff[handoff_key]
        for environment_key, handoff_key in digest_fields.items()
    },
    "DIRECT_RUNTIME_DEFINES_JSON": json.dumps(
        defines,
        ensure_ascii=False,
        separators=(",", ":"),
    ),
}
for key, value in exports.items():
    print(f"export {key}={shlex.quote(str(value))}")
PY
  )" || {
    echo "[ios-dart-defines] GATE_BLOCK: canonical launcher handoff is invalid." >&2
    exit 2
  }
  eval "$CANONICAL_HANDOFF_EXPORTS"
  ENV_NAME="$QWQ_APP_RUNTIME_ENV"
  LAUNCH_MODE="$QWQ_APP_LAUNCH_MODE"
  echo "[ios-dart-defines] using canonical launcher handoff for $QWQ_LAUNCH_TARGET." >&2
fi
DIRECT_ENVIRONMENT="${QWQ_ENVIRONMENT:-${QWQ_APP_RUNTIME_ENV:-${EXISTING_RUNTIME_ENV:-alpha}}}"
DIRECT_TARGET="${DIRECT_ENVIRONMENT}-local"
LAUNCH_POLICY="${QWQ_APP_LAUNCH_POLICY:-${EXISTING_LAUNCH_POLICY:-test_live}}"

if [[ -z "$LAUNCH_MODE" \
   && "${CONFIGURATION:-}" == Debug* \
   && ("${PLATFORM_NAME:-}" == "iphonesimulator" || "${PLATFORM_NAME:-}" == "iphoneos") \
   && -z "${QWQ_LAUNCH_TARGET:-}" \
   && -z "${QWQ_DART_DEFINES_DIGEST:-}" \
   && -z "${QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST:-}" \
   && -z "${QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST:-}" ]]; then
  case "$DIRECT_ENVIRONMENT" in
    alpha|beta|gamma) ;;
    *)
      echo "[ios-dart-defines] GATE_BLOCK: direct Debug flavor must be alpha|beta|gamma." >&2
      exit 2
      ;;
  esac
  if [[ -n "${QWQ_ENVIRONMENT:-}" \
     && -n "$EXISTING_RUNTIME_ENV" \
     && "$QWQ_ENVIRONMENT" != "$EXISTING_RUNTIME_ENV" ]]; then
    echo "[ios-dart-defines] GATE_BLOCK: QWQ_ENVIRONMENT conflicts with APP_RUNTIME_ENV in DART_DEFINES." >&2
    exit 2
  fi
  DIRECT_PYTHON="$RUNTIME_PYTHON"
  if ! DIRECT_PREFLIGHT_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 "$DIRECT_PYTHON" \
      "$APP_DIR/../quwoquan_ops/cli/stackctl.py" --output-format json \
      app-debug-preflight --target "$DIRECT_TARGET" --runtime-mode test_live
  )"; then
    echo "$DIRECT_PREFLIGHT_JSON" >&2
    DIRECT_PREFLIGHT_BLOCKER="$(
      PYTHONDONTWRITEBYTECODE=1 "$DIRECT_PYTHON" - \
        "$DIRECT_PREFLIGHT_JSON" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except (IndexError, json.JSONDecodeError):
    raise SystemExit(0)
details = payload.get("details")
if isinstance(details, list):
    for detail in details:
        value = str(detail or "").strip()
        if value:
            print(value)
            break
PY
    )"
    if [[ -n "$DIRECT_PREFLIGHT_BLOCKER" ]]; then
      echo "[ios-dart-defines] GATE_BLOCK: first blocker: $DIRECT_PREFLIGHT_BLOCKER" >&2
    else
      echo "[ios-dart-defines] GATE_BLOCK: target runtime/readiness preflight did not pass." >&2
    fi
    echo "[ios-dart-defines] Resolve the reported runtime/readiness blocker, then retry the same flutter run command." >&2
    exit 2
  fi
  DIRECT_PREFLIGHT_EXPORTS="$(
    PYTHONDONTWRITEBYTECODE=1 "$DIRECT_PYTHON" - "$DIRECT_PREFLIGHT_JSON" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
if payload.get("status") not in {"passed", "warning"}:
    raise SystemExit("App Debug preflight did not allow test_live")
for warning in payload.get("warnings") or []:
    print(f"[ios-dart-defines] WARN: {warning}", file=sys.stderr)
PY
  )" || {
    echo "[ios-dart-defines] GATE_BLOCK: App content preflight returned an invalid receipt." >&2
    exit 2
  }
  eval "$DIRECT_PREFLIGHT_EXPORTS"
  DIRECT_HANDOFF_COMMAND=(
    "$DIRECT_PYTHON"
    "$APP_DIR/scripts/device/build_launcher_handoff.py"
    --env "$DIRECT_ENVIRONMENT"
    --target "$DIRECT_TARGET"
    --launch-mode direct_flutter_run
    --launch-policy test_live
    --app-instance-id direct-flutter-run
    --app-instance-namespace direct-flutter-run
  )
  if ! DIRECT_HANDOFF_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 "${DIRECT_HANDOFF_COMMAND[@]}"
  )"; then
    echo "[ios-dart-defines] GATE_BLOCK: canonical direct Debug handoff could not be built." >&2
    exit 2
  fi
  DIRECT_HANDOFF_EXPORTS="$(
    PYTHONDONTWRITEBYTECODE=1 "$DIRECT_PYTHON" - "$DIRECT_HANDOFF_JSON" <<'PY'
import json
import shlex
import sys

handoff = json.loads(sys.argv[1])
values = {
    "QWQ_APP_RUNTIME_ENV": handoff["environment"],
    "QWQ_APP_LAUNCH_MODE": handoff["launchMode"],
    "QWQ_APP_LAUNCH_POLICY": handoff["launchPolicy"],
    "QWQ_LAUNCH_TARGET": handoff["target"],
    "QWQ_DART_DEFINES_DIGEST": handoff["dartDefinesDigest"],
    "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST": handoff["runtimeConfigDigest"],
    "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": handoff[
        "effectiveLaunchManifestDigest"
    ],
    "DIRECT_RUNTIME_DEFINES_JSON": json.dumps(
        handoff["dartDefines"],
        ensure_ascii=False,
        separators=(",", ":"),
    ),
}
for key, value in values.items():
    print(f"export {key}={shlex.quote(str(value))}")
PY
  )" || {
    echo "[ios-dart-defines] GATE_BLOCK: canonical direct Debug handoff is invalid." >&2
    exit 2
  }
  eval "$DIRECT_HANDOFF_EXPORTS"
  ENV_NAME="$QWQ_APP_RUNTIME_ENV"
  LAUNCH_MODE="$QWQ_APP_LAUNCH_MODE"
  LAUNCH_POLICY="$QWQ_APP_LAUNCH_POLICY"
  echo "[ios-dart-defines] direct Debug uses canonical $DIRECT_TARGET handoff." >&2
  if [[ "${PLATFORM_NAME:-}" == "iphonesimulator" \
     && -n "${QWQ_RUN_CONSUMER_ID:-}" ]]; then
    DIRECT_SIMULATOR_UDID="$(
      PYTHONPATH="$APP_DIR/.." PYTHONDONTWRITEBYTECODE=1 "$DIRECT_PYTHON" - \
        "${QWQ_IOS_SIMULATOR_UDID:-${TARGET_DEVICE_IDENTIFIER:-}}" <<'PY'
import sys
from quwoquan_ops.cli.lib.local_device_trust import resolve_managed_device

print(resolve_managed_device("ios-simulator", sys.argv[1]))
PY
    )" || {
      echo "[ios-dart-defines] GATE_BLOCK: direct Debug requires one explicit booted Simulator." >&2
      exit 2
    }
    if ! PYTHONDONTWRITEBYTECODE=1 "$DIRECT_PYTHON" \
      "$APP_DIR/../quwoquan_ops/cli/stackctl.py" --output-format json \
      device-trust --target "$DIRECT_TARGET" --platform ios-simulator \
      --action install --device "$DIRECT_SIMULATOR_UDID" \
      --lease-id "direct-flutter-run:${DIRECT_SIMULATOR_UDID}" \
      --defer-endpoint-probe >/dev/null; then
      echo "[ios-dart-defines] WARN: Simulator trust is unavailable; test_live continues with typed network recovery." >&2
    fi
    if ! PYTHONDONTWRITEBYTECODE=1 "$DIRECT_PYTHON" \
      "$APP_DIR/../quwoquan_ops/cli/stackctl.py" --output-format json \
      consumer-lease acquire --target "$DIRECT_TARGET" \
      --platform ios-simulator --device "$DIRECT_SIMULATOR_UDID" \
      --consumer "direct-flutter-run" \
      --bundle-id "${PRODUCT_BUNDLE_IDENTIFIER:-}" \
      --ports "" \
      --handoff-digest "$QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST" >/dev/null; then
      echo "[ios-dart-defines] WARN: Simulator runtime lease is unavailable; compile-first test_live continues." >&2
    fi
  elif [[ "${PLATFORM_NAME:-}" == "iphonesimulator" ]]; then
    echo "[ios-dart-defines] WARN: compile-only Debug does not own Simulator trust or a runtime lease; use run.sh for a device-bound test_live session." >&2
  fi
fi

if [[ ("$LAUNCH_MODE" == "canonical_launcher" \
    || "$LAUNCH_MODE" == "environment_patrol_smoke") \
   && -z "${QWQ_LAUNCH_HANDOFF_JSON:-}" ]]; then
  echo "[ios-dart-defines] GATE_BLOCK: $LAUNCH_MODE requires QWQ_LAUNCH_HANDOFF_JSON." >&2
  exit 2
fi

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

# App package identity is immutable build input selected by the Xcode flavor
# configuration before this phase runs. This phase only verifies that the selected
# configuration and canonical handoff agree; it never mutates future build settings.
if [[ -n "${PRODUCT_BUNDLE_IDENTIFIER:-}" ]]; then
  case "${CONFIGURATION:-}" in
    Debug-*) QWQ_EXPECTED_BUILD_MODE="debug"; QWQ_EXPECTED_CONFIGURATION_PREFIX="Debug" ;;
    Profile-*) QWQ_EXPECTED_BUILD_MODE="profile"; QWQ_EXPECTED_CONFIGURATION_PREFIX="Profile" ;;
    Release-*) QWQ_EXPECTED_BUILD_MODE="release"; QWQ_EXPECTED_CONFIGURATION_PREFIX="Release" ;;
    *)
      echo "[ios-dart-defines] GATE_BLOCK: iOS builds must use a generated <BuildMode>-<environment> configuration." >&2
      exit 2
      ;;
  esac
  QWQ_EXPECTED_BUNDLE_ID="$(
    PYTHONPATH="$APP_DIR/..${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
      "$RUNTIME_PYTHON" -c "from quwoquan_ops.cli.lib.app_identity import application_id_for; import sys; print(application_id_for('ios', sys.argv[1], sys.argv[2]))" \
      "$ENV_NAME" "$QWQ_EXPECTED_BUILD_MODE"
  )" || {
    echo "[ios-dart-defines] GATE_BLOCK: failed to derive the expected bundle id for environment=$ENV_NAME buildMode=$QWQ_EXPECTED_BUILD_MODE." >&2
    exit 2
  }
  QWQ_EXPECTED_CONFIGURATION_NAME="$QWQ_EXPECTED_CONFIGURATION_PREFIX-$ENV_NAME"
  if [[ "${CONFIGURATION:-}" != "$QWQ_EXPECTED_CONFIGURATION_NAME" ]]; then
    echo "[ios-dart-defines] GATE_BLOCK: Xcode configuration ${CONFIGURATION:-<missing>} does not match environment=$ENV_NAME buildMode=$QWQ_EXPECTED_BUILD_MODE; select flavor $ENV_NAME before rebuilding." >&2
    exit 2
  fi
  if [[ "$PRODUCT_BUNDLE_IDENTIFIER" != "$QWQ_EXPECTED_BUNDLE_ID" ]]; then
    echo "[ios-dart-defines] GATE_BLOCK: resolved bundle id $PRODUCT_BUNDLE_IDENTIFIER does not match $QWQ_EXPECTED_BUNDLE_ID for environment=$ENV_NAME; generated flavor identity is stale." >&2
    exit 2
  fi
fi

if [[ -z "$LAUNCH_MODE" ]]; then
  echo "[ios-dart-defines] GATE_BLOCK: canonical launch mode is required; use ./run.sh -d <device>." >&2
  exit 2
fi

if [[ -n "$DIRECT_RUNTIME_DEFINES_JSON" ]]; then
  RUNTIME_DEFINES_JSON="$DIRECT_RUNTIME_DEFINES_JSON"
else
  RUNTIME_DEFINES_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 "$RUNTIME_PYTHON" \
      "$APP_DIR/scripts/env/print_app_env_dart_defines.py" \
      --env "$ENV_NAME" \
      --format json \
      --launch-mode "$LAUNCH_MODE" \
      --launch-policy "$LAUNCH_POLICY"
  )"
fi

"$RUNTIME_PYTHON" - \
  "$RUNTIME_DEFINES_JSON" \
  "${DART_DEFINES:-}" \
  "$APP_DIR" <<'PY'
import base64
import json
import os
import shlex
import sys
from pathlib import Path

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
    "APP_LAUNCH_POLICY",
}
native_runtime_keys = required_keys | {"QWQ_APP_LAUNCH_MODE"}

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

app_dir = Path(sys.argv[3]).resolve()
main_entrypoint = "lib/main_prod.dart"
flutter_target = os.environ.get("FLUTTER_TARGET", "").strip()
patrol_enabled = merged.get("RUN_PATROL_ACCEPTANCE", "").strip().lower() == "true"
if patrol_enabled:
    print(
        "[ios-dart-defines] APP.PACKAGE.production_test_dependency_leak: "
        "Patrol belongs to quwoquan_app/test_host/patrol.",
        file=sys.stderr,
    )
    raise SystemExit(5)
effective_flutter_target = main_entrypoint
native_entrypoint = main_entrypoint
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
                "entrypoint": native_entrypoint,
                "launchMode": runtime_defines.get("QWQ_APP_LAUNCH_MODE", ""),
                "launchPolicy": runtime_defines.get("APP_LAUNCH_POLICY", ""),
                "runtimeDefines": {
                    key: merged[key]
                    for key in sorted(native_runtime_keys)
                    if merged.get(key, "").strip()
                },
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
print("export FLUTTER_TARGET=" + shlex.quote(effective_flutter_target))
print("export DART_DEFINES=" + shlex.quote(",".join(encoded_defines)))
print("export QWQ_IOS_DART_DEFINES_READY=1")
PY
