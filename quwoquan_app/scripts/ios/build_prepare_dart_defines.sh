#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STACKCTL_PYTHON_RESOLVER="$APP_DIR/scripts/ios/build_resolve_stackctl_python.sh"
RUNTIME_PYTHON="$(bash "$STACKCTL_PYTHON_RESOLVER")" || {
  echo "[ios-runtime-config] GATE_BLOCK: build requires Python 3.10+ with PyYAML." >&2
  exit 2
}

case "${CONFIGURATION:-}" in
  Debug-nonprod) BUILD_PROFILE="nonprod"; BUILD_MODE="debug" ;;
  Profile-nonprod) BUILD_PROFILE="nonprod"; BUILD_MODE="profile" ;;
  Release-nonprod) BUILD_PROFILE="nonprod"; BUILD_MODE="release" ;;
  Release-prod) BUILD_PROFILE="prod"; BUILD_MODE="release" ;;
  Debug-prod|Profile-prod)
    echo "[ios-runtime-config] GATE_BLOCK: prod AppArtifact supports Release-prod only; Debug and Profile use Debug-nonprod/Profile-nonprod." >&2
    exit 2
    ;;
  *)
    echo "[ios-runtime-config] GATE_BLOCK: iOS configuration must be Debug-nonprod, Profile-nonprod, Release-nonprod, or Release-prod." >&2
    exit 2
    ;;
esac

if [[ -z "${QWQ_APP_BUILD_PROFILE:-}" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: generated build-profile identity is missing." >&2
  exit 2
fi
if [[ "$QWQ_APP_BUILD_PROFILE" != "$BUILD_PROFILE" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: QWQ_APP_BUILD_PROFILE conflicts with ${CONFIGURATION:-}." >&2
  exit 2
fi

VALIDATION_EXPORTS="$($RUNTIME_PYTHON - "${DART_DEFINES:-}" "${FLUTTER_TARGET:-}" "$APP_DIR" <<'PY'
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
main_entrypoint = (app_dir / "lib/main_prod.dart").resolve()
requested = sys.argv[2].strip()
if requested:
    requested_path = Path(requested)
    if not requested_path.is_absolute():
        requested_path = app_dir / requested_path
    if requested_path.resolve() != main_entrypoint:
        raise SystemExit("FLUTTER_TARGET must remain lib/main_prod.dart")
print("export FLUTTER_TARGET=" + shlex.quote("lib/main_prod.dart"))
print("export DART_DEFINES=" + shlex.quote(existing or "__QWQ_COMPILE_ONLY__"))
PY
)" || {
  echo "[ios-runtime-config] GATE_BLOCK: compile inputs contain runtime configuration." >&2
  exit 2
}
eval "$VALIDATION_EXPORTS"

if [[ -n "${PRODUCT_BUNDLE_IDENTIFIER:-}" ]]; then
  EXPECTED_BUNDLE_ID="$({
    PYTHONPATH="$APP_DIR/..${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
      "$RUNTIME_PYTHON" -c \
      "from quwoquan_ops.cli.lib.app_identity import resolve_app_identity; import sys; print(resolve_app_identity(platform='ios', build_profile=sys.argv[1], build_mode=sys.argv[2]).application_id)" \
      "$BUILD_PROFILE" "$BUILD_MODE"
  })" || {
    echo "[ios-runtime-config] GATE_BLOCK: failed to derive build-product bundle identity." >&2
    exit 2
  }
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

RUNTIME_TRUST_PATH="${QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH:-}"
if [[ -z "$RUNTIME_TRUST_PATH" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: build-profile runtime trust envelope is required for every iOS AppArtifact." >&2
  exit 2
fi
if [[ -z "${TARGET_BUILD_DIR:-}" || -z "${UNLOCALIZED_RESOURCES_FOLDER_PATH:-}" ]]; then
  echo "[ios-runtime-config] GATE_BLOCK: Xcode resource output is required to materialize the trust envelope." >&2
  exit 2
fi

"$RUNTIME_PYTHON" - \
  "$RUNTIME_TRUST_PATH" "$BUILD_PROFILE" \
  "$TARGET_BUILD_DIR" "$UNLOCALIZED_RESOURCES_FOLDER_PATH" <<'PY'
import base64
import json
import os
import re
import shutil
import sys
from pathlib import Path

trust_path = Path(sys.argv[1]).expanduser()
build_profile = sys.argv[2]
if not trust_path.is_absolute() or trust_path.is_symlink() or not trust_path.is_file():
    raise SystemExit("runtime trust envelope must be an absolute regular non-symlink file")
if trust_path.stat().st_size <= 0 or trust_path.stat().st_size > 1024 * 1024:
    raise SystemExit("runtime trust envelope size is invalid")
try:
    trust = json.loads(trust_path.read_text(encoding="utf-8"))
except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"runtime trust envelope is malformed: {exc}")
required = {
    "schema",
    "schemaVersion",
    "buildProfile",
    "signatureAlgorithm",
    "trustedPublicKeys",
}
if not isinstance(trust, dict) or set(trust) != required:
    raise SystemExit("runtime trust envelope fields do not match the canonical schema")
if (
    trust.get("schema") != "app-runtime-config-trust"
    or trust.get("schemaVersion") != "1"
    or trust.get("buildProfile") != build_profile
    or trust.get("signatureAlgorithm") != "ed25519"
):
    raise SystemExit("runtime trust envelope identity conflicts with Xcode configuration")
keyring = trust.get("trustedPublicKeys")
if not isinstance(keyring, dict) or not keyring:
    raise SystemExit("runtime trust envelope keyring is missing")
key_id_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
for key_id, encoded_key in keyring.items():
    if not isinstance(key_id, str) or key_id_pattern.fullmatch(key_id) is None:
        raise SystemExit("runtime trust envelope contains an invalid key id")
    if not isinstance(encoded_key, str):
        raise SystemExit("runtime trust envelope public key must be base64 text")
    try:
        raw_key = base64.b64decode(encoded_key, validate=True)
    except ValueError as exc:
        raise SystemExit("runtime trust envelope public key is not strict base64") from exc
    if len(raw_key) != 32 or base64.b64encode(raw_key).decode("ascii") != encoded_key:
        raise SystemExit("runtime trust envelope public key is not canonical Ed25519")
resource_root = Path(sys.argv[3]) / sys.argv[4] / "qwq_runtime"
resource_root.mkdir(parents=True, exist_ok=True)
package_destination = resource_root / "runtime-config-package.json"
if package_destination.exists() or package_destination.is_symlink():
    package_destination.unlink()
destination = resource_root / "runtime-config-trust.json"
temporary = destination.with_suffix(destination.suffix + ".tmp")
shutil.copyfile(trust_path, temporary)
os.chmod(temporary, 0o600)
temporary.replace(destination)
PY

export FLUTTER_TARGET DART_DEFINES
export QWQ_IOS_DART_DEFINES_READY=1
echo "[ios-runtime-config] buildProduct=ios-${BUILD_PROFILE}-app compileRuntimeDefines=0 embeddedRuntimePackage=0" >&2
printf 'export FLUTTER_TARGET=%q\n' "$FLUTTER_TARGET"
printf 'export DART_DEFINES=%q\n' "$DART_DEFINES"
printf 'export QWQ_IOS_DART_DEFINES_READY=1\n'
