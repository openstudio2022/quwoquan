#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

hook_src="$ROOT/githooks/pre-commit"
hook_dst="$ROOT/.git/hooks/pre-commit"

if [[ ! -d "$ROOT/.git/hooks" ]]; then
  echo "[hooks] not a git repo: $ROOT" 1>&2
  exit 2
fi

cp "$hook_src" "$hook_dst"
chmod +x "$hook_dst"

echo "[hooks] installed: $hook_dst"
echo "[hooks] note: runs gate on staged changes under quwoquan_app/ or quwoquan_service/"

