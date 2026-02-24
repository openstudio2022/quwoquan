#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

scope="all"
if [[ "${1:-}" == "--scope" ]]; then
  scope="${2:-}"
fi

run_service() {
  echo "[gate] quwoquan_service"
  bash scripts/verify_feature_traceability.sh
  bash scripts/verify_contract_metadata.sh
  bash scripts/verify_acceptance_standard.sh
  bash scripts/verify_specs_l1_hierarchy.sh
  bash scripts/verify_feature_tree_refactor.sh
  bash scripts/verify_engineering_directory.sh
  bash scripts/verify_opsx_ff_8services_consistency.sh
  bash scripts/verify_runtime_packaging.sh
  (cd quwoquan_service && make gate)
}

run_app() {
  echo "[gate] quwoquan_app"
  command -v flutter >/dev/null 2>&1 || { echo "[gate] FAIL: flutter not found in PATH" 1>&2; exit 1; }
  (cd quwoquan_app && flutter pub get)
  (cd quwoquan_app && flutter analyze)
  if [[ "${GITHUB_ACTIONS:-}" == "true" || "${QWQ_GATE_TESTS:-}" == "1" ]]; then
    (cd quwoquan_app && flutter test)
  else
    echo "[gate] skip flutter test (set QWQ_GATE_TESTS=1 or run in CI)"
  fi
}

echo "[gate] repo quality gate (scope=$scope)"

case "$scope" in
  all)
    run_service
    run_app
    ;;
  service)
    run_service
    ;;
  app)
    run_app
    ;;
  *)
    echo "[gate] FAIL: invalid scope: $scope (expected all|service|app)" 1>&2
    exit 2
    ;;
esac

echo "[gate] OK"

