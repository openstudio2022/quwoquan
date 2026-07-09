#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$SERVICE_ROOT/.." && pwd)"
cd "$REPO_ROOT"

echo "[compat] forwarding to root script: quwoquan_ops/gate/scaffold/install-hooks.sh"
bash quwoquan_ops/gate/scaffold/install-hooks.sh

