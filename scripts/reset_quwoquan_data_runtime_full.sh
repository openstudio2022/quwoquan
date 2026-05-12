#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUNTIME="${QWQ_RUNTIME_ROOT:-$ROOT/quwoquan_data/runtime}"
TMP_BACKUP="$(mktemp -d)"
trap 'rm -rf "$TMP_BACKUP"' EXIT

echo "[data-reset] runtime=$RUNTIME"
echo "[data-reset] backup tracked runtime baseline"

TRACKED_PREFIX="quwoquan_data/runtime/"
while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  sub="${rel#$TRACKED_PREFIX}"
  src="$ROOT/$rel"
  if [[ -f "$src" ]]; then
    mkdir -p "$TMP_BACKUP/$(dirname "$sub")"
    cp "$src" "$TMP_BACKUP/$sub"
  fi
done < <(git -c core.quotePath=false ls-files -- quwoquan_data/runtime)

echo "[data-reset] rm -rf $RUNTIME"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"

if [[ -d "$TMP_BACKUP" ]]; then
  (cd "$TMP_BACKUP" && find . -type f -print0) | while IFS= read -r -d '' file; do
    target="${RUNTIME%/}/${file#./}"
    mkdir -p "$(dirname "$target")"
    cp "$TMP_BACKUP/${file#./}" "$target"
  done
fi

python3 - <<'PY'
import os
import sys
from pathlib import Path

root = Path(os.environ.get("QWQ_DATA_ROOT", Path("quwoquan_data").resolve()))
sys.path.insert(0, str(root / "tools"))
from common import ensure_runtime_layout  # noqa: E402

ensure_runtime_layout()
PY

echo "[data-reset] restored tracked baseline and recreated runtime layout"
