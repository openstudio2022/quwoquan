#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INPUT_PATH="${1:-"$ROOT_DIR/quwoquan_service/runtime/persona/testdata/rehearsal_input.json"}"
SWITCH_LATENCY_MS="${PERSONA_SWITCH_LATENCY_MS:-18.4}"

cd "$ROOT_DIR/quwoquan_service"
go run ./tools/persona_rollout --input "$INPUT_PATH" --switch-latency-ms "$SWITCH_LATENCY_MS"
