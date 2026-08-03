#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREPARE_SCRIPT="$APP_DIR/scripts/ios/prepare_dart_defines.sh"

set +e
prepared_exports="$(bash "$PREPARE_SCRIPT")"
status=$?
set -e
if [[ "$status" -ne 0 ]]; then
  echo "[ios-build] GATE_BLOCK: runtime package preparation failed; resolve the first typed blocker reported above, then retry the same Flutter command." >&2
  exit "$status"
fi

eval "$prepared_exports"
if [[ "${QWQ_IOS_DART_DEFINES_READY:-}" != "1" || -z "${DART_DEFINES:-}" ]]; then
  echo "[ios-build] GATE_BLOCK: runtime package preparation did not produce verified Dart defines." >&2
  exit 3
fi

resolved_flutter_root="${FLUTTER_ROOT:-}"
if [[ -z "$resolved_flutter_root" ]]; then
  resolved_flutter_root="$(
    grep -E '^FLUTTER_ROOT=' "$APP_DIR/ios/Flutter/Generated.xcconfig" | cut -d= -f2-
  )"
fi
if [[ -z "$resolved_flutter_root" ]]; then
  echo "[ios-build] GATE_BLOCK: FLUTTER_ROOT is unavailable." >&2
  exit 4
fi

exec /bin/sh "$resolved_flutter_root/packages/flutter_tools/bin/xcode_backend.sh" build
