#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${APP_ROOT}"
exec python3 scripts/ios/ios_shortcut_log_hygiene.py run -- "$@"
