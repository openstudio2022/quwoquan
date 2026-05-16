#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

scope="all"
if [[ "${1:-}" == "--scope" ]]; then
  scope="${2:-}"
fi

if [ -d "$ROOT/scripts" ]; then
  echo "[gate] FAIL: root scripts/ directory must not exist — scripts belong in quwoquan_app/scripts/, quwoquan_service/scripts/, quwoquan_data/scripts/, or agent_ops/" >&2
  exit 1
fi

run_service() {
  echo "[gate] quwoquan_service"
  bash agent_ops/scaffold/verify_feature_traceability.sh
  bash quwoquan_service/scripts/contract/verify_contract_metadata.sh
  bash agent_ops/scaffold/verify_acceptance_standard.sh
  bash agent_ops/scaffold/verify_specs_l1_hierarchy.sh
  bash agent_ops/scaffold/verify_feature_tree_refactor.sh
  bash agent_ops/scaffold/verify_engineering_directory.sh
  bash quwoquan_service/scripts/deploy/verify_opsx_ff_8services_consistency.sh
  bash quwoquan_service/scripts/runtime/verify_runtime_packaging.sh
  bash quwoquan_service/scripts/deploy/verify_ff_config_contract.sh
  python3 quwoquan_app/scripts/runtime/verify_module_package_mapping.py
  python3 quwoquan_service/scripts/recommendation/verify_reliable_task_catalog.py
  python3 quwoquan_service/scripts/recommendation/verify_reliable_task_retention_policy.py
  python3 quwoquan_service/scripts/runtime/verify_module_permission_scope.py
  python3 quwoquan_service/scripts/recommendation/verify_reliable_task_migration.py
  # topology 由 delivery-gate topology job / make gate 负责，避免重复
  bash quwoquan_service/scripts/deploy/verify_deploy_kustomization.sh
  bash quwoquan_service/scripts/recommendation/verify_recommendation_service_contract.sh
  bash quwoquan_service/scripts/deploy/verify_config_gray_parallel_binding.sh
  bash quwoquan_service/scripts/deploy/verify_gray_rollout_stages.sh
  # Config release guardrails (skeleton; strict mode via QWQ_CONFIG_GATE_STRICT=1)
  bash quwoquan_service/scripts/runtime/verify_service_config_layout.sh
  bash quwoquan_service/scripts/runtime/verify_service_env_contract.sh
  bash quwoquan_service/scripts/deploy/verify_config_release_version_mapping.sh
  bash quwoquan_service/scripts/deploy/verify_config_image_compat.sh
  bash quwoquan_service/scripts/deploy/verify_config_pr_policy.sh
  command -v dart >/dev/null 2>&1 || { echo "[gate] FAIL: dart not found in PATH" 1>&2; exit 1; }
  dart tools/runtime_error_codegen/bin/generate_runtime_errors.dart --check
  dart tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart
  (cd quwoquan_service && make gate)
  (cd quwoquan_service/services/product-ops-service && go test ./cmd/api ./tests -count=1)
}

run_app() {
  echo "[gate] quwoquan_app"
  command -v flutter >/dev/null 2>&1 || { echo "[gate] FAIL: flutter not found in PATH" 1>&2; exit 1; }
  command -v dart >/dev/null 2>&1 || { echo "[gate] FAIL: dart not found in PATH" 1>&2; exit 1; }
  dart tools/runtime_error_codegen/bin/generate_runtime_errors.dart --check
  dart tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart
  (cd quwoquan_app && flutter pub get)
  (cd quwoquan_app && flutter analyze --no-fatal-warnings --no-fatal-infos)
  # Dart 语义门禁：视觉 token + iOS 语义风格（chevron / Cupertino 组件边界）
  if command -v python3 >/dev/null 2>&1; then
    python3 quwoquan_app/scripts/runtime/verify_retired_terms_zero.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_dart_semantic.py || exit 1
    python3 quwoquan_app/scripts/settings/verify_settings_canonical.py || exit 1
    python3 quwoquan_app/scripts/chat/verify_conversation_sheet_canonical.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_error_code_semantic.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_cloud_services_semantic.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_route_and_context_semantic.py || exit 1
    python3 agent_ops/assistant/verify_no_personal_assistant_imports.py || exit 1
    python3 agent_ops/assistant/verify_assistant_old_stack_retired.py || exit 1
    # L0 PA 降级响应契约静态分析（阻断）：
    #   - degraded:true 必须有 errorCode
    #   - finalText 不得泄漏 JSON envelope key
    #   - catch 块必须保留 $error 根因信息
    #   - acceptance.yaml 引用的测试文件必须存在
    python3 agent_ops/assistant/verify_degraded_response_contract.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_ios_native_surface_gate.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_page_horizontal_quality_matrix.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_page_matrix_scan_complete.py || exit 1
    # 页面 A/B/C：默认 --quiet 仅汇总、不阻断；GATE_PAGE_ABC_ENFORCE 见 specs/gates/page_abc_governance.md
    if [[ -n "${GATE_PAGE_ABC_ENFORCE:-}" ]]; then
      _abc_flags=""
      _gpe=$(echo "${GATE_PAGE_ABC_ENFORCE}" | tr '[:upper:]' '[:lower:]')
      _gpe=${_gpe//,/ }
      for _tok in ${_gpe}; do
        case "${_tok}" in
          abc)
            _abc_flags="${_abc_flags} --enforce-a --enforce-b --enforce-c"
            ;;
          ab)
            _abc_flags="${_abc_flags} --enforce-a --enforce-b"
            ;;
          ac)
            _abc_flags="${_abc_flags} --enforce-a --enforce-c"
            ;;
          bc)
            _abc_flags="${_abc_flags} --enforce-b --enforce-c"
            ;;
          a)
            _abc_flags="${_abc_flags} --enforce-a"
            ;;
          b)
            _abc_flags="${_abc_flags} --enforce-b"
            ;;
          c)
            _abc_flags="${_abc_flags} --enforce-c"
            ;;
        esac
      done
      # shellcheck disable=SC2086
      python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --quiet ${_abc_flags} || exit 1
    else
      python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --quiet
    fi
    # 助手手写 + App 搜索仓库：弱类型棘轮（见 specs/gates/assistant_search_weak_typing_governance.md）
    python3 agent_ops/avatar/verify_assistant_search_weak_typing_ratchet.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_metadata_driven_ui_gate.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_metadata_routes_vs_codegen_app.py || exit 1
    python3 quwoquan_service/scripts/contract/verify_metadata_service_entities_vs_fields.py || exit 1
    python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py || exit 1
    python3 quwoquan_app/scripts/env/verify_contract_mock_data_inventory.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_app_no_integration_test_dir.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_lib_no_import_test_tree.py || exit 1
    python3 quwoquan_app/scripts/env/verify_ui_app_data_source_mode_ratchet.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_lib_no_test_only_symbols.py || exit 1
    python3 quwoquan_app/scripts/env/verify_app_seed_manifests.py || exit 1
    python3 quwoquan_app/scripts/env/verify_business_env_data_inventory.py || exit 1
    python3 quwoquan_app/scripts/content/verify_pageflip_backward_mainline.py || exit 1
    python3 quwoquan_service/scripts/gamma/verify_gamma_validation_profiles.py || exit 1
    python3 agent_ops/ci/verify_ci_profile_consistency.py || exit 1
  else
    echo "[gate] WARN: python3 not found — skipping verify_dart_semantic, verify_settings_canonical, verify_conversation_sheet_canonical, verify_error_code_semantic, verify_cloud_services_semantic, verify_route_and_context_semantic, verify_no_personal_assistant_imports, verify_degraded_response_contract, verify_ios_native_surface_gate, verify_page_horizontal_quality_matrix, verify_page_matrix_scan_complete, verify_page_abc_governance, verify_assistant_search_weak_typing_ratchet, verify_metadata_driven_ui_gate, verify_metadata_routes_vs_codegen_app, verify_metadata_service_entities_vs_fields, verify_ui_mock_isolation, verify_contract_mock_data_inventory, verify_app_no_integration_test_dir, verify_lib_no_import_test_tree, verify_ui_app_data_source_mode_ratchet, verify_lib_no_test_only_symbols, verify_app_seed_manifests, verify_business_env_data_inventory, verify_pageflip_backward_mainline"
  fi
  # L1 content tests (L1a contract, L1b widget, L1c journey) — fast, no external deps
  # Paths follow: test/{layer}/{domain}/{entity}/{test_type}/ (see .cursor/rules/03-testing.mdc §3)
  # 使用 tee 边跑边输出：原先整段输出进变量，长时间无日志易被误判为「卡住」。
  local flutter_log
  flutter_log="$(mktemp -t quwoquan_gate_flutter_l1.XXXXXX)"
  local flutter_status=0
  set +e
  set -o pipefail
  (cd quwoquan_app && flutter test test/cloud/ test/components/ test/core/ test/ui/ test/smoke/ 2>&1 | tee "$flutter_log")
  flutter_status=${PIPESTATUS[0]:-1}
  set +o pipefail
  set -e
  if [[ "$flutter_status" -ne 0 ]]; then
    if grep -Fq "Connection closed before full header was received" "$flutter_log" 2>/dev/null; then
      echo ""
      echo "[gate] FAIL: flutter_tester loopback bootstrap failed — Proxifier Network Extension is intercepting 127.0.0.1 TCP connections."
      echo ""
      echo "[gate] ROOT CAUSE DIAGNOSIS:"
      echo "  Proxifier (com.initex.proxifier.v3.macos.ProxifierExtension) is active and redirecting"
      echo "  ALL TCP connections (including loopback 127.0.0.1) to the Clash Verge proxy at 127.0.0.1:7899."
      echo "  flutter_tester connects to flutter tools HTTP listener on a random 127.0.0.1 port, but"
      echo "  Proxifier intercepts it before the server can accept, causing the WebSocket upgrade to fail."
      echo ""
      echo "[gate] FIX — Proxifier rules UI (one-time setup, permanent fix):"
      echo "  1. Open Proxifier.app → menu: Profile → Rules…"
      echo "  2. Click '+' to add a new rule at the TOP of the list"
      echo "  3. Set rule name: 'Localhost Direct'"
      echo "  4. Applications: <Any>"
      echo "  5. Target hosts: 127.0.0.1; ::1; localhost"
      echo "  6. Target ports: <Any>"
      echo "  7. Action: Direct"
      echo "  8. Click OK and save profile"
      echo ""
      echo "  After adding the rule, re-run: make gate"
      echo ""
      echo "[gate] ALTERNATIVE (temporary — for single test session):"
      echo "  Quit Proxifier.app before running 'make gate', then reopen after."
      echo ""
    fi
    rm -f "$flutter_log"
    return 1
  fi
  rm -f "$flutter_log"
  # PA Core（桶 A 协议契约 + 桶 B 引擎集成 + 桶 C UI 契约）默认全部阻断。
  # 桶 A 覆盖降级响应根因/消息记录协议/可观测字段，失败即退。
  bash agent_ops/assistant/run_pa_core_tests.sh
  # Skip in CI: test/patrol/ (needs real device/Patrol, run via FTL).

  # dart_func 覆盖率检查：mock.yaml 声明的 dart_func 必须在 Dart 测试文件中存在
  if command -v python3 >/dev/null 2>&1; then
    python3 quwoquan_app/scripts/runtime/verify_dart_func_coverage.py || exit 1
  else
    echo "[gate] WARN: python3 not found — skipping dart_func coverage check"
  fi
}

run_portal() {
  echo "[gate] ops-portal"
  command -v npm >/dev/null 2>&1 || { echo "[gate] FAIL: npm not found in PATH" 1>&2; exit 1; }
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  npm run ops-portal:test
  npm run ops-portal:build
}

echo "[gate] repo quality gate (scope=$scope)"

run_patrol_local() {
  # L4 Patrol（本地调试用，CI 由 FTL workflow 承载）
  if ! command -v patrol >/dev/null 2>&1; then
    echo "[gate] SKIP: patrol CLI not found — L4 skipped (install: dart pub global activate patrol_cli)"
    return 0
  fi
  echo "[gate] L4 Patrol (local device)"
  (cd quwoquan_app && patrol test test/patrol/ --dart-define=APP_RUNTIME_ENV=gamma --dart-define=API_CONTRACT_ENV=gamma)
}

case "$scope" in
  all)
    run_service
    run_app
    run_portal
    ;;
  service)
    run_service
    ;;
  app)
    run_app
    ;;
  portal|ops-portal)
    run_portal
    ;;
  patrol)
    run_patrol_local
    ;;
  *)
    echo "[gate] FAIL: invalid scope: $scope (expected all|service|app|portal|patrol)" 1>&2
    exit 2
    ;;
esac

echo "[gate] OK"

