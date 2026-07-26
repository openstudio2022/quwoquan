#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ACTION="${1:-up}"

case "$ACTION" in
  up|down) ;;
  *)
    echo "usage: $0 {up|down}" >&2
    exit 2
    ;;
esac

PYTHONDONTWRITEBYTECODE=1 python3 "$ROOT_DIR/quwoquan_ops/cli/alpha/content_release_runtime.py" "$ACTION"
