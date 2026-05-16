#!/usr/bin/env bash
# F5: optional CI — regenerate assistant-related Dart from metadata and fail if git diff is non-empty.
# Usage (from repo root): QWQ_ASSISTANT_CODEGEN_GATE=1 ./scripts/verify_assistant_codegen_clean.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT/quwoquan_service"

if [[ "${QWQ_ASSISTANT_CODEGEN_GATE:-}" != "1" ]]; then
  echo "[verify_assistant_codegen_clean] skip (set QWQ_ASSISTANT_CODEGEN_GATE=1 to enable)"
  exit 0
fi

go run ./tools/codegen_app_metadata \
  -metadata-dir contracts/metadata \
  -app-dir ../quwoquan_app

cd "$ROOT"
if ! git diff --quiet -- \
  quwoquan_app/lib/cloud/runtime/generated/assistant/ \
  quwoquan_app/lib/assistant/generated/; then
  echo "[verify_assistant_codegen_clean] FAIL: assistant codegen drift — run from repo root:" >&2
  echo "  cd quwoquan_service && go run ./tools/codegen_app_metadata -metadata-dir contracts/metadata -app-dir ../quwoquan_app" >&2
  git diff -- quwoquan_app/lib/cloud/runtime/generated/assistant/ quwoquan_app/lib/assistant/generated/ >&2 || true
  exit 1
fi

echo "[verify_assistant_codegen_clean] OK"
