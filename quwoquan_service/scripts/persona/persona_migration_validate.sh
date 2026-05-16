#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INPUT_PATH="${1:-"$ROOT_DIR/quwoquan_service/runtime/persona/testdata/rehearsal_input.json"}"
OUTPUT_PATH="${2:-}"

cd "$ROOT_DIR/quwoquan_service"
if [[ -n "$OUTPUT_PATH" ]]; then
  go run ./tools/persona_rollout --input "$INPUT_PATH" > "$OUTPUT_PATH"
else
  go run ./tools/persona_rollout --input "$INPUT_PATH"
fi
