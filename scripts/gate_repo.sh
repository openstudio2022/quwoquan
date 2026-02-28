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
  bash scripts/verify_ff_config_contract.sh
  bash scripts/verify_deployment_domain_mapping.sh
  bash scripts/verify_recommendation_service_contract.sh
  bash scripts/verify_topology_contract_regression.sh
  # Config release guardrails (skeleton; strict mode via QWQ_CONFIG_GATE_STRICT=1)
  bash scripts/verify_service_config_layout.sh
  bash scripts/verify_service_env_contract.sh
  bash scripts/verify_config_release_version_mapping.sh
  bash scripts/verify_config_image_compat.sh
  bash scripts/verify_config_pr_policy.sh
  (cd quwoquan_service && make gate)
}

run_app() {
  echo "[gate] quwoquan_app"
  command -v flutter >/dev/null 2>&1 || { echo "[gate] FAIL: flutter not found in PATH" 1>&2; exit 1; }
  (cd quwoquan_app && flutter pub get)
  (cd quwoquan_app && flutter analyze --no-fatal-warnings --no-fatal-infos)
  # Always run L1 content tests (L1a contract, L1b widget, L1c journey) — fast, no external deps
  # Paths follow: test/{layer}/{domain}/{entity}/{test_type}/ (see .cursor/rules/03-testing.mdc §3)
  (cd quwoquan_app && flutter test test/cloud/ test/components/ test/ui/)
  # Full test suite (includes acceptance VM tests requiring LLM + external services) — CI only
  if [[ "${GITHUB_ACTIONS:-}" == "true" || "${QWQ_GATE_TESTS:-}" == "1" ]]; then
    (cd quwoquan_app && flutter test)
  fi

  # dart_func 覆盖率检查：mock.yaml 声明的 dart_func 必须在 Dart 测试文件中存在
  if command -v python3 >/dev/null 2>&1; then
    python3 scripts/verify_dart_func_coverage.py || exit 1
  else
    echo "[gate] WARN: python3 not found — skipping dart_func coverage check"
  fi
}

echo "[gate] repo quality gate (scope=$scope)"

run_patrol_local() {
  # L4 Patrol（本地调试用，CI 由 FTL workflow 承载）
  if ! command -v patrol >/dev/null 2>&1; then
    echo "[gate] SKIP: patrol CLI not found — L4 skipped (install: dart pub global activate patrol_cli)"
    return 0
  fi
  echo "[gate] L4 Patrol (local device)"
  (cd quwoquan_app && patrol test test/patrol/ --dart-define=ENV=staging)
}

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
  patrol)
    run_patrol_local
    ;;
  *)
    echo "[gate] FAIL: invalid scope: $scope (expected all|service|app|patrol)" 1>&2
    exit 2
    ;;
esac

echo "[gate] OK"

