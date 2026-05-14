#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$SERVICE_ROOT/.." && pwd)"
cd "$REPO_ROOT"

echo "[compat] forwarding to root script: agent_ops/scaffold/install-hooks.sh"
bash agent_ops/scaffold/install-hooks.sh

