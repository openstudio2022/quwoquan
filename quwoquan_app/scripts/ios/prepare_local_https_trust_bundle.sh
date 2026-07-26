#!/usr/bin/env bash
set -euo pipefail

# Dart HttpClient maintains its own TLS trust store on iOS Simulator.  The
# Simulator keychain alone therefore cannot establish the local Gamma/Alpha
# HTTPS plane for Remote composition.  This build phase packages the canonical
# local target trust bundle only for Debug/Profile simulator builds that
# explicitly use a localhost authority.

case "${CONFIGURATION:-Debug}" in
  Debug|Profile) ;;
  *) exit 0 ;;
esac

if [[ "${EFFECTIVE_PLATFORM_NAME:-}" != *"iphonesimulator"* &&
      "${PLATFORM_NAME:-}" != "iphonesimulator" ]]; then
  exit 0
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"

read_define() {
  local key="$1"
  DART_DEFINES="${DART_DEFINES:-}" DEFINE_KEY="$key" python3 - <<'PY'
import base64
import os

key = os.environ["DEFINE_KEY"] + "="
for item in filter(None, os.environ.get("DART_DEFINES", "").split(",")):
    try:
        decoded = base64.b64decode(item).decode("utf-8", errors="replace")
    except Exception:
        continue
    if decoded.startswith(key):
        print(decoded[len(key):].strip())
        break
PY
}

gateway_base_url="$(read_define CLOUD_GATEWAY_BASE_URL)"
runtime_env="$(read_define APP_RUNTIME_ENV)"
gateway_host="$(
  GATEWAY_BASE_URL="$gateway_base_url" python3 - <<'PY'
from urllib.parse import urlparse
import os

parsed = urlparse(os.environ.get("GATEWAY_BASE_URL", ""))
print((parsed.hostname or "").lower())
PY
)"

case "$gateway_host" in
  localhost|*.localhost) ;;
  *) exit 0 ;;
esac

case "$runtime_env" in
  alpha) local_target="alpha-local" ;;
  beta) local_target="beta-local" ;;
  gamma) local_target="gamma-local" ;;
  prod) local_target="prod-sim" ;;
  *)
    echo "[ios-local-https] GATE_BLOCK: localhost gateway requires a supported APP_RUNTIME_ENV; got ${runtime_env:-<empty>}" >&2
    exit 2
    ;;
esac

certificate_path="$(
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - "$local_target" <<'PY'
import sys

from quwoquan_ops.cli.lib.local_target_tls import materialize_local_target_trust_bundle

print(materialize_local_target_trust_bundle(sys.argv[1]))
PY
)"

if ! openssl crl2pkcs7 -nocrl -certfile "$certificate_path" -outform DER >/dev/null 2>&1; then
  echo "[ios-local-https] GATE_BLOCK: canonical local trust bundle is invalid: $certificate_path" >&2
  exit 2
fi

resource_dir="${TARGET_BUILD_DIR:?TARGET_BUILD_DIR is required}/${UNLOCALIZED_RESOURCES_FOLDER_PATH:?UNLOCALIZED_RESOURCES_FOLDER_PATH is required}"
destination="$resource_dir/local_env_debug_root.crt"
mkdir -p "$resource_dir"
install -m 0644 "$certificate_path" "$destination"
echo "[ios-local-https] bundled trusted roots for $local_target"
