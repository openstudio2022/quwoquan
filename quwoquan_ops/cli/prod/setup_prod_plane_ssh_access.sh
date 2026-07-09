#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec python3 "$ROOT_DIR/quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.py" "$@"
