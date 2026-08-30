#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREPARE_SCRIPT="$APP_DIR/scripts/ios/build_prepare_dart_defines.sh"

set +e
prepared_exports="$(bash "$PREPARE_SCRIPT")"
status=$?
set -e
if [[ "$status" -ne 0 ]]; then
  echo "[ios-build] GATE_BLOCK: trust envelope preparation failed; resolve the first typed blocker reported above, then retry the same Flutter command." >&2
  exit "$status"
fi

eval "$prepared_exports"
if [[ "${QWQ_IOS_DART_DEFINES_READY:-}" != "1" || -z "${DART_DEFINES:-}" ]]; then
  echo "[ios-build] GATE_BLOCK: trust envelope preparation did not produce verified compile inputs." >&2
  exit 3
fi

# SDK 单轨：canonical launcher/facade 贯穿 QWQ_REAL_FLUTTER 时以其 SDK 根为准；
# 既有 FLUTTER_ROOT/Generated.xcconfig 解析降级为 fail-closed 同源校验，
# 两个来源指向不同 SDK 时阻断而不是静默二选一。
resolved_flutter_root="${FLUTTER_ROOT:-}"
if [[ -z "$resolved_flutter_root" ]]; then
  resolved_flutter_root="$(
    grep -E '^FLUTTER_ROOT=' "$APP_DIR/ios/Flutter/Generated.xcconfig" | cut -d= -f2-
  )"
fi
if [[ -n "${QWQ_REAL_FLUTTER:-}" ]]; then
  real_flutter_root="$(cd "$(dirname "$QWQ_REAL_FLUTTER")/.." && pwd)" || {
    echo "[ios-build] GATE_BLOCK: QWQ_REAL_FLUTTER does not resolve to a Flutter SDK root." >&2
    exit 4
  }
  if [[ -n "$resolved_flutter_root" ]]; then
    legacy_flutter_root="$(cd "$resolved_flutter_root" 2>/dev/null && pwd)" || legacy_flutter_root=""
    if [[ -n "$legacy_flutter_root" && "$legacy_flutter_root" != "$real_flutter_root" ]]; then
      echo "[ios-build] GATE_BLOCK: QWQ_REAL_FLUTTER ($real_flutter_root) conflicts with FLUTTER_ROOT ($legacy_flutter_root); the launch chain must consume one Flutter SDK." >&2
      exit 4
    fi
  fi
  resolved_flutter_root="$real_flutter_root"
fi
if [[ -z "$resolved_flutter_root" ]]; then
  echo "[ios-build] GATE_BLOCK: FLUTTER_ROOT is unavailable." >&2
  exit 4
fi

exec /bin/sh "$resolved_flutter_root/packages/flutter_tools/bin/xcode_backend.sh" build
