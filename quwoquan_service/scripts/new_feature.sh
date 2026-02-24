#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$SERVICE_ROOT/.." && pwd)"
cd "$REPO_ROOT"

slug="${1:-}"
if [[ -z "$slug" ]]; then
  echo "usage: bash quwoquan_service/scripts/new_feature.sh <slug>" 1>&2
  echo "example: bash quwoquan_service/scripts/new_feature.sh discovery-feed-v1" 1>&2
  exit 2
fi

echo "[compat] forwarding to root script: scripts/new_feature_fullstack.sh"
bash scripts/new_feature_fullstack.sh "$slug"

