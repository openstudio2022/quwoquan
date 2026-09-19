#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACKCTL_PYTHON_RESOLVER="$APP_DIR/scripts/ios/build_resolve_stackctl_python.sh"
TRUST_BLOCKER="APP.LAUNCH.runtime_config_trust_missing"

RUNTIME_PYTHON="$(bash "$STACKCTL_PYTHON_RESOLVER")" || exit 2
IDENTITY_EXPORTS="$(PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$APP_DIR/..${PYTHONPATH:+:$PYTHONPATH}" \
  "$RUNTIME_PYTHON" - "${CONFIGURATION:-}" <<'PY'
import shlex
import sys
from quwoquan_ops.cli.lib.app_identity import resolve_ios_configuration
try:
    identity = resolve_ios_configuration(sys.argv[1])
except ValueError as error:
    raise SystemExit(f"[ios-runtime-config] GATE_BLOCK: {error}")
for key, value in {"BUILD_PROFILE": identity.build_profile, "BUILD_MODE": identity.build_mode,
                   "BUILD_ENVIRONMENT": identity.environment or "",
                   "EXPECTED_BUNDLE_ID": identity.application_id}.items():
    print(key + "=" + shlex.quote(value))
PY
)" || exit 2
eval "$IDENTITY_EXPORTS"
if [[ -n "$BUILD_ENVIRONMENT" && -n "${QWQ_APP_RUNTIME_ENV:-}" && "$QWQ_APP_RUNTIME_ENV" != "$BUILD_ENVIRONMENT" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: generated environment conflicts with configuration." >&2
  exit 2
fi

if [[ -z "${QWQ_APP_BUILD_PROFILE:-}" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: generated build-profile identity is missing." >&2
  exit 2
fi
if [[ "$QWQ_APP_BUILD_PROFILE" != "$BUILD_PROFILE" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: QWQ_APP_BUILD_PROFILE conflicts with ${CONFIGURATION:-}." >&2
  exit 2
fi

# trust 是 AppArtifact 的第一道制品门：先于 Flutter backend 与任何编译动作判否，确保
# raw Xcode 也得到与 canonical executor 相同的 typed blocker。
# Debug-alpha 构建期自供给（REQ-003 build_time_self_supply）：无外部 canonical handoff
# 时，以当前源码树（SRCROOT 推导的 APP_DIR，不读任何用户级配置）调用仓内 canonical
# handoff builder 签发独立 Alpha offline bootstrap + nonprod trust，并以激活请求形态嵌入
# 制品；Profile/Release 与 prod 仍 fail-closed。
RUNTIME_TRUST_PATH="${QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH:-}"
SELF_SUPPLY_REQUEST_PATH=""
SELF_SUPPLY_ROOT=""
cleanup_self_supply() {
  if [[ -n "$SELF_SUPPLY_ROOT" ]]; then
    rm -rf -- "$SELF_SUPPLY_ROOT"
  fi
}
trap cleanup_self_supply EXIT
if [[ -z "${TARGET_BUILD_DIR:-}" || -z "${UNLOCALIZED_RESOURCES_FOLDER_PATH:-}" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: $TRUST_BLOCKER: Xcode resource output is required to materialize the trust envelope." >&2
  exit 2
fi

# Flutter 有时传 absolute target；只按同一 App 根归一，不按 ambient 环境猜测。
NORMALIZED_FLUTTER_TARGET="$($RUNTIME_PYTHON - "$APP_DIR" "${FLUTTER_TARGET:-lib/main.dart}" <<'PY'
from pathlib import Path
import sys
app = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2])
if not target.is_absolute():
    target = app / target
print(target.resolve().relative_to(app).as_posix())
PY
)" || exit 2
if [[ -z "$RUNTIME_TRUST_PATH" && "${CONFIGURATION:-}" == "Debug-alpha" \
   && ( "$NORMALIZED_FLUTTER_TARGET" == "lib/main.dart" || "$NORMALIZED_FLUTTER_TARGET" == "lib/main_alpha.dart" ) ]]; then
  SELF_SUPPLY_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/qwq-ios-self-supply.XXXXXX")"
  chmod 0700 "$SELF_SUPPLY_ROOT"
  RUNTIME_TRUST_PATH="$SELF_SUPPLY_ROOT/runtime-config-trust.json"
  SELF_SUPPLY_REQUEST_PATH="$SELF_SUPPLY_ROOT/runtime-config-self-supply-request.json"
  if ! SELF_SUPPLY_SUMMARY="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$APP_DIR/..${PYTHONPATH:+:$PYTHONPATH}" \
      "$RUNTIME_PYTHON" "$APP_DIR/scripts/device/build_self_supply_request.py" \
        --trust-output "$RUNTIME_TRUST_PATH" \
        --request-output "$SELF_SUPPLY_REQUEST_PATH"
  )"; then
    echo "[ios-runtime-config] GATE_BLOCK: $TRUST_BLOCKER: Debug-alpha build-time self supply failed (see the typed blocker above)." >&2
    exit 2
  fi
  echo "[ios-runtime-config] runtimeConfigSupplyMode=build_time_self_supply $(printf '%s' "$SELF_SUPPLY_SUMMARY" | "$RUNTIME_PYTHON" -c 'import json,sys; d=json.load(sys.stdin); print("requestDigest="+d["requestDigest"], "packageDigest="+d["packageDigest"])')" >&2
fi
if [[ -z "$RUNTIME_TRUST_PATH" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: $TRUST_BLOCKER: build-profile runtime trust envelope is required for every ${CONFIGURATION:-} iOS AppArtifact." >&2
  echo "[ios-runtime-config] launch through ./quwoquan_app/run.sh -d <device>; the canonical launcher materializes the trust envelope." >&2
  exit 2
fi

VALIDATION_EXPORTS="$($RUNTIME_PYTHON - "${DART_DEFINES:-}" "${FLUTTER_TARGET:-}" "$APP_DIR" "$BUILD_ENVIRONMENT" "$BUILD_MODE" "$BUILD_PROFILE" <<'PY'
import base64
import shlex
import sys
from pathlib import Path

forbidden = {
    "APP_RUNTIME_ENV",
    "APP_LAUNCH_TARGET",
    "APP_LAUNCH_POLICY",
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
    "QWQ_LAUNCH_TARGET",
    "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
    "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
}
existing = sys.argv[1].strip()
decoded_defines: dict[str, str] = {}
for encoded in filter(None, existing.split(",")):
    if encoded == "__QWQ_COMPILE_ONLY__":
        continue
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except Exception as exc:
        raise SystemExit(f"DART_DEFINES contains invalid base64: {exc}")
    if "=" not in decoded:
        raise SystemExit("DART_DEFINES contains an invalid define")
    key, value = decoded.split("=", 1)
    decoded_defines[key] = value
violations = sorted(key for key in forbidden if key in decoded_defines)
if violations:
    raise SystemExit(
        "runtime configuration is forbidden in DART_DEFINES: " + ", ".join(violations)
    )
if decoded_defines.get("RUN_PATROL_ACCEPTANCE", "").strip().lower() == "true":
    raise SystemExit(
        "APP.PACKAGE.production_test_dependency_leak: Patrol belongs to quwoquan_app/test_host/patrol"
    )
app_dir = Path(sys.argv[3]).resolve()
sys.path.insert(0, str(app_dir.parent))
from quwoquan_ops.cli.lib.app_launch_manifest_contract import load_launch_manifest_contract
contract = load_launch_manifest_contract()
mapping = contract["content_source_entrypoints"]
environment, mode = sys.argv[4:6]
expected = mapping[contract["content_source_policy"][environment]] if environment else None
if mode == "release" and sys.argv[6] == "prod":
    expected = mapping[contract["content_source_policy"]["prod"]]
requested = sys.argv[2].strip()
if mode == "profile" and not requested:
    raise SystemExit("Profile requires explicit FLUTTER_TARGET")
requested = requested or expected or "lib/main.dart"
requested_path = Path(requested)
if not requested_path.is_absolute():
    requested_path = app_dir / requested_path
if requested_path.resolve() == (app_dir / "lib/main.dart").resolve():
    requested_path = app_dir / (expected or mapping["bundled_snapshot"])
if expected and requested_path.resolve() != (app_dir / expected).resolve():
    raise SystemExit("FLUTTER_TARGET conflicts with canonical environment content source")
allowed = {(app_dir / value).resolve(): value for value in mapping.values()}
if requested_path.resolve() not in allowed:
    raise SystemExit("FLUTTER_TARGET must match canonical source entrypoint")
print("export FLUTTER_TARGET=" + shlex.quote(allowed[requested_path.resolve()]))
print("export DART_DEFINES=" + shlex.quote(existing or "__QWQ_COMPILE_ONLY__"))
PY
)" || {
  echo "[ios-runtime-config] GATE_BLOCK: compile inputs contain runtime configuration." >&2
  exit 2
}
eval "$VALIDATION_EXPORTS"

if [[ -n "${PRODUCT_BUNDLE_IDENTIFIER:-}" ]]; then
  if [[ "$PRODUCT_BUNDLE_IDENTIFIER" != "$EXPECTED_BUNDLE_ID" ]]; then
    echo "[ios-runtime-config] GATE_BLOCK: bundle id $PRODUCT_BUNDLE_IDENTIFIER does not match $EXPECTED_BUNDLE_ID for ios-${BUILD_PROFILE}-app." >&2
    exit 2
  fi
fi

if [[ -n "${QWQ_IOS_RUNTIME_CONFIG_PACKAGE_PATH:-}" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: target runtime package must be activated post-install and must not enter Runner.app." >&2
  exit 2
fi
if [[ -n "${QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON:-}" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: manual trusted-public-keys JSON is retired; supply one profile trust envelope file." >&2
  exit 2
fi

# trust 嵌入与 Patrol UAT test host 共用同一份实现，宿主与生产因此受同一组判否约束。
# 嵌 trust envelope；Debug-alpha 自供给时另嵌激活请求。可读 runtime package 不进入 Runner.app。
EMBED_ARGUMENTS=(
  "$RUNTIME_TRUST_PATH" "$BUILD_PROFILE"
  "$TARGET_BUILD_DIR" "$UNLOCALIZED_RESOURCES_FOLDER_PATH"
)
if [[ -n "$SELF_SUPPLY_REQUEST_PATH" ]]; then
  EMBED_ARGUMENTS+=(--self-supply-request "$SELF_SUPPLY_REQUEST_PATH")
fi
if ! "$RUNTIME_PYTHON" "$APP_DIR/scripts/ios/build_embed_runtime_config_trust.py" \
  "${EMBED_ARGUMENTS[@]}"; then
  echo "[ios-runtime-config] GATE_BLOCK: $TRUST_BLOCKER: build-profile runtime trust envelope is invalid." >&2
  exit 2
fi

export FLUTTER_TARGET DART_DEFINES
export QWQ_IOS_DART_DEFINES_READY=1
echo "[ios-runtime-config] buildProduct=ios-${BUILD_PROFILE}-app compileRuntimeDefines=0 embeddedRuntimePackage=0 selfSupplyRequest=$([[ -n "$SELF_SUPPLY_REQUEST_PATH" ]] && echo 1 || echo 0)" >&2
printf 'export FLUTTER_TARGET=%q\n' "$FLUTTER_TARGET"
printf 'export DART_DEFINES=%q\n' "$DART_DEFINES"
printf 'export QWQ_IOS_DART_DEFINES_READY=1\n'
