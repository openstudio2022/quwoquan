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
EXISTING_LAUNCH_POLICY="$(
  python3 - "${DART_DEFINES:-}" <<'PY'
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
    "CONTENT_BINDING_STATE",
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
    "CONTENT_BINDING_STATE": str(handoff.get("contentBindingState") or ""),
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

content_fields = {
    "QWQ_CONTENT_RELEASE_ID": "contentReleaseId",
    "QWQ_CONTENT_MANIFEST_DIGEST": "contentManifestDigest",
    "QWQ_CONTENT_READINESS_RECEIPT_DIGEST": "contentReadinessReceiptDigest",
}
content_values = [str(handoff.get(field) or "") for field in content_fields.values()]
binding_state = str(handoff.get("contentBindingState") or "")
if binding_state == "bound" and not all(content_values):
    fail("bound canonical launcher handoff has incomplete content identity")
if binding_state == "unbound" and any(content_values):
    fail("unbound canonical launcher handoff contains content identity")
if binding_state not in {"bound", "unbound"}:
    fail("canonical launcher handoff contentBindingState is invalid")

identity_fields = {
    "QWQ_APP_RUNTIME_ENV": "environment",
    "QWQ_LAUNCH_TARGET": "target",
    "QWQ_APP_LAUNCH_MODE": "launchMode",
    "QWQ_APP_LAUNCH_POLICY": "launchPolicy",
    **digest_fields,
    **content_fields,
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
    **{
        environment_key: str(handoff.get(handoff_key) or "")
        for environment_key, handoff_key in content_fields.items()
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
DIRECT_ENVIRONMENT="${QWQ_ENVIRONMENT:-${EXISTING_RUNTIME_ENV:-alpha}}"
case "$DIRECT_ENVIRONMENT" in
  alpha|beta|gamma) ;;
  *)
    echo "[ios-dart-defines] GATE_BLOCK: QWQ_ENVIRONMENT must be alpha|beta|gamma." >&2
    exit 2
    ;;
esac
DIRECT_TARGET="${DIRECT_ENVIRONMENT}-local"
LAUNCH_POLICY="${QWQ_APP_LAUNCH_POLICY:-${EXISTING_LAUNCH_POLICY:-test_live}}"

if [[ -z "$LAUNCH_MODE" \
   && "${CONFIGURATION:-}" == Debug* \
   && ("${PLATFORM_NAME:-}" == "iphonesimulator" || "${PLATFORM_NAME:-}" == "iphoneos") \
   && -z "${QWQ_LAUNCH_TARGET:-}" \
   && -z "${QWQ_DART_DEFINES_DIGEST:-}" \
   && -z "${QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST:-}" \
   && -z "${QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST:-}" ]]; then
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
for key, field in (
    ("QWQ_CONTENT_RELEASE_ID", "releaseId"),
    ("QWQ_CONTENT_MANIFEST_DIGEST", "manifestDigest"),
    ("QWQ_CONTENT_READINESS_RECEIPT_DIGEST", "readinessReceiptDigest"),
):
    value = str(payload.get(field) or "").strip()
    if value:
        print(f"export {key}={shlex.quote(value)}")
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
  if [[ -n "${QWQ_CONTENT_RELEASE_ID:-}" ]]; then
    DIRECT_HANDOFF_COMMAND+=(
      --content-release-id "$QWQ_CONTENT_RELEASE_ID"
      --content-manifest-digest "$QWQ_CONTENT_MANIFEST_DIGEST"
      --content-readiness-receipt-digest
      "$QWQ_CONTENT_READINESS_RECEIPT_DIGEST"
    )
  fi
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
    "QWQ_CONTENT_RELEASE_ID": handoff["contentReleaseId"],
    "QWQ_CONTENT_MANIFEST_DIGEST": handoff["contentManifestDigest"],
    "QWQ_CONTENT_READINESS_RECEIPT_DIGEST": handoff[
        "contentReadinessReceiptDigest"
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
      --bundle-id "${PRODUCT_BUNDLE_IDENTIFIER:-com.example.quwoquanApp}" \
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

python3 - \
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
content_release_id = os.environ.get("QWQ_CONTENT_RELEASE_ID", "").strip()
content_manifest_digest = os.environ.get(
    "QWQ_CONTENT_MANIFEST_DIGEST",
    "",
).strip()
content_readiness_receipt_digest = os.environ.get(
    "QWQ_CONTENT_READINESS_RECEIPT_DIGEST",
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
if runtime_defines.get("APP_LAUNCH_POLICY", "") == "prod_release":
    if not content_release_id:
        print(
            "[ios-dart-defines] FAIL: release-bound contentReleaseId is required.",
            file=sys.stderr,
        )
        raise SystemExit(5)
    for label, value in (
        ("QWQ_CONTENT_MANIFEST_DIGEST", content_manifest_digest),
        (
            "QWQ_CONTENT_READINESS_RECEIPT_DIGEST",
            content_readiness_receipt_digest,
        ),
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
    "CONTENT_BINDING_STATE",
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
    if not flutter_target:
        print(
            "[ios-dart-defines] FAIL: Patrol build requires FLUTTER_TARGET.",
            file=sys.stderr,
        )
        raise SystemExit(5)
    target_path = Path(flutter_target)
    if not target_path.is_absolute():
        target_path = app_dir / target_path
    target_path = target_path.resolve()
    canonical_patrol_entrypoint = (
        app_dir / "test/user_acceptance/patrol/test_bundle.dart"
    ).resolve()
    if target_path != canonical_patrol_entrypoint or not target_path.is_file():
        print(
            "[ios-dart-defines] FAIL: Patrol build must use the canonical "
            "test/user_acceptance/patrol/test_bundle.dart entrypoint.",
            file=sys.stderr,
        )
        raise SystemExit(5)
    effective_flutter_target = flutter_target
    native_entrypoint = target_path.relative_to(app_dir).as_posix()
else:
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
    content_binding = {
        "contentReleaseId": content_release_id,
        "contentManifestDigest": content_manifest_digest,
        "contentReadinessReceiptDigest": content_readiness_receipt_digest,
    }
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
                "contentBindingState": runtime_defines.get(
                    "CONTENT_BINDING_STATE", ""
                ),
                "runtimeDefines": {
                    key: merged[key]
                    for key in sorted(native_runtime_keys)
                    if merged.get(key, "").strip()
                },
                "recoveryBaseURL": merged["CLOUD_GATEWAY_BASE_URL"],
                "publicWebURL": merged["PUBLIC_WEB_BASE_URL"],
                "appDownloadBaseURL": merged["APP_DOWNLOAD_BASE_URL"],
                **{
                    key: value
                    for key, value in content_binding.items()
                    if value
                },
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
