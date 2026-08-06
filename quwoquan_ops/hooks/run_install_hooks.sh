#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

hook_dir="$ROOT/quwoquan_ops/hooks"

if [[ ! -d "$hook_dir" ]]; then
  echo "[hooks] missing hook directory: $hook_dir" 1>&2
  exit 2
fi

git config core.hooksPath quwoquan_ops/hooks
chmod +x "$hook_dir"/pre-commit "$hook_dir"/pre-push

echo "[hooks] installed via core.hooksPath=quwoquan_ops/hooks"
echo "[hooks] note: pre-commit blocks non-whitelisted branches before commit; pre-push blocks pushes to non-whitelisted branches"
