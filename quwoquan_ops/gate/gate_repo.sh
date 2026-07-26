#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONPYCACHEPREFIX="$ROOT/.qwq_output/env/repo/local/repo-gate/cache/bytecode"
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -o cache_dir=$ROOT/.qwq_output/env/repo/local/tests/cache/pytest"
export QWQ_PYTHON_CACHE_ROOT="${QWQ_PYTHON_CACHE_ROOT:-$HOME/.cache/quwoquan/python-envs}"

if [ -x "/opt/homebrew/opt/ruby/bin/ruby" ]; then
  export PATH="/opt/homebrew/opt/ruby/bin:$PATH"
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import yaml
PY
then
  if [ -x "/opt/homebrew/bin/python3" ] && /opt/homebrew/bin/python3 - <<'PY' >/dev/null 2>&1
import yaml
PY
  then
    export PATH="/opt/homebrew/bin:$PATH"
  elif [ -x "$QWQ_PYTHON_CACHE_ROOT/quwoquan-data/bin/python3" ] && "$QWQ_PYTHON_CACHE_ROOT/quwoquan-data/bin/python3" - <<'PY' >/dev/null 2>&1
import yaml
PY
  then
    export PATH="$QWQ_PYTHON_CACHE_ROOT/quwoquan-data/bin:$PATH"
  fi
fi

scope="all"
if [[ "${1:-}" == "--scope" ]]; then
  scope="${2:-}"
fi

if [ -d "$ROOT/scripts" ]; then
  echo "[gate] FAIL: root scripts/ directory must not exist — scripts belong in quwoquan_app/scripts/, quwoquan_service/scripts/, quwoquan_data/scripts/, or quwoquan_ops/" >&2
  exit 1
fi

run_global() {
  bash quwoquan_ops/gate/scaffold/verify_global_increment_constraints.sh
  python3 quwoquan_ops/gate/verify_git_branch_policy.py
  python3 quwoquan_ops/gate/verify_github_supply_chain.py
  python3 quwoquan_ops/gate/verify_github_artifact_lifecycle.py
  python3 quwoquan_ops/gate/verify_agent_context_contract.py
  python3 quwoquan_ops/gate/verify_retired_runtime_architecture.py
  python3 quwoquan_ops/gate/verify_single_track_contracts.py
  python3 quwoquan_ops/gate/verify_behavior_event_type_contract.py
  python3 quwoquan_ops/cli/cloud_contract_handoff.py verify
  python3 quwoquan_app/scripts/runtime/verify_app_generated_manifest.py
  python3 quwoquan_app/scripts/runtime/verify_cloud_package_boundaries.py
  python3 quwoquan_ops/cli/feature_tree.py verify
  python3 quwoquan_ops/gate/verify_execution_profiles.py
  python3 quwoquan_ops/gate/scaffold/verify_test_directory_layout.py
  python3 quwoquan_ops/gate/scaffold/verify_test_no_fake.py
  python3 quwoquan_ops/gate/verify_local_dependency_purity.py
  python3 quwoquan_ops/gate/verify_observability_layout.py
  python3 quwoquan_ops/gate/verify_observability_envelope.py
  python3 quwoquan_app/scripts/runtime/verify_content_page_funnel_coverage.py
  python3 quwoquan_ops/tests/local_contract/test_content_page_funnel_coverage__observability__local_contract_test.py
  python3 quwoquan_ops/gate/verify_runtime_log_governance.py
  python3 quwoquan_ops/gate/verify_output_layout.py
  python3 quwoquan_ops/gate/verify_output_path_source_contract.py
  python3 quwoquan_ops/gate/verify_external_provider_governance.py
  python3 quwoquan_ops/gate/verify_provider_conformance_evidence.py
  python3 quwoquan_ops/gate/verify_entrypoint_script_paths.py
  python3 quwoquan_ops/gate/verify_markdown_local_links.py
  # 丢弃误写入源码树的 Python 缓存，再跑 root layout（缓存只允许落在 .qwq_output）。
  find "$ROOT" \
    \( -path "$ROOT/.git" -o -path "$ROOT/.qwq_output" \) -prune -o \
    \( -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -exec rm -rf {} + \)
  rm -rf "$ROOT/.pytest_cache"
  python3 quwoquan_ops/gate/verify_root_layout.py
  python3 quwoquan_app/scripts/runtime/verify_app_layout.py
  python3 quwoquan_data/scripts/verify/verify_data_layout.py
}

# App CI 的 static 作业唯一执行仓库级与静态门禁；tests 分片只执行互斥的
# 测试集合。默认本地 all、其它 scope 与 static phase 仍完整执行全局门禁。
if [[ "$scope" != "app" || "${QWQ_APP_GATE_PHASE:-all}" != "tests" ]]; then
  run_global
fi

run_service() {
  echo "[gate] quwoquan_service"
  python3 quwoquan_ops/cli/feature_tree.py verify
  python3 quwoquan_ops/gate/verify_stackctl_args_contract.py
  python3 quwoquan_ops/gate/verify_stackctl_provider_readiness_contract.py
python3 quwoquan_ops/gate/verify_dev_up_cli_surface.py
python3 quwoquan_ops/gate/verify_api_path_unversioned.py
python3 quwoquan_ops/gate/verify_environment_assembly.py
  python3 quwoquan_ops/gate/verify_local_env_port_manifest.py
  python3 quwoquan_ops/gate/verify_prod_rollout_stackctl_contract.py
  python3 quwoquan_ops/gate/verify_prod_plane_access_isolation.py
  python3 quwoquan_ops/gate/verify_prod_access_guard.py
  bash quwoquan_service/scripts/contract/verify_contract_metadata.sh
  python3 quwoquan_service/scripts/contract/verify_tag_ref_source_of_truth.py
  # 内容域评论计数自洽（缺口A 防回归）：真相源 + 派生产物（*.lite.json / *.gamma-curated.json）
  # 的 commentCount/replyCount 不得与裁剪后评论集漂移（派生由 bundle 生成器在裁剪后重算保证）
  python3 quwoquan_service/scripts/contract/verify_content_fixture_comment_counts.py --include-derived
  bash quwoquan_ops/environments/verify/verify_service_domain_layout.sh
  bash quwoquan_service/scripts/runtime/verify_runtime_packaging.sh
  bash quwoquan_ops/environments/verify/verify_ff_config_contract.sh
  python3 quwoquan_ops/gate/verify_service_architecture.py
  python3 quwoquan_service/scripts/recommendation/verify_reliable_task_catalog.py
  python3 quwoquan_service/scripts/recommendation/verify_reliable_task_retention_policy.py
  python3 quwoquan_service/scripts/runtime/verify_module_permission_scope.py
  python3 quwoquan_service/scripts/recommendation/verify_reliable_task_migration.py
  # topology 由 delivery-gate topology job / make gate 负责，避免重复
  bash quwoquan_ops/environments/verify/verify_deploy_kustomization.sh
  bash quwoquan_service/scripts/recommendation/verify_recommendation_service_contract.sh
  python3 quwoquan_service/scripts/recommendation/verify_daily_metrics_dimension_consistency.py
  # N2-2 gamma-local 推荐 policy overlay 与 metadata baseline 的受控差异守卫
  # （允许差异仅 objectCards.enabled / policyVersion，防第二真相源漂移）
  python3 quwoquan_ops/gate/verify_gamma_policy_overlay.py
  bash quwoquan_ops/environments/verify/verify_config_gray_parallel_binding.sh
  bash quwoquan_ops/environments/verify/verify_gray_rollout_stages.sh
  # 灰度路由策略（版本/userId/省份/运营商四维）schema 与枚举
  python3 quwoquan_ops/environments/verify/verify_gray_routing_policy.py
  # Config release guardrails (skeleton; strict mode via QWQ_CONFIG_GATE_STRICT=1)
  bash quwoquan_service/scripts/runtime/verify_service_config_layout.sh
  python3 quwoquan_ops/gate/verify_runtime_config_release_layout.py
  bash quwoquan_service/scripts/runtime/verify_service_env_contract.sh
  python3 quwoquan_service/scripts/verify/verify_login_dependency_config.py
  python3 quwoquan_service/scripts/verify/verify_relationship_error_code_gate.py
  python3 quwoquan_service/scripts/verify/verify_error_recovery_alignment.py
  python3 quwoquan_ops/tests/local_contract/test_content_object_alert_coverage__contract_graph_mapping__observability__local_contract_test.py
  python3 quwoquan_service/scripts/verify/verify_content_object_alert_coverage.py
  python3 quwoquan_service/scripts/verify/verify_entity_object_alert_coverage.py
  python3 quwoquan_service/scripts/verify/verify_entity_homepage_object_mainline.py
  python3 quwoquan_app/scripts/env/verify_public_vs_upstream_url_contract.py
  bash quwoquan_ops/environments/verify/verify_service_config_digest_mapping.sh
  bash quwoquan_ops/environments/verify/verify_config_image_compat.sh
  bash quwoquan_ops/environments/verify/verify_config_pr_policy.sh
  make verify-env-packaging
  # 环境包生成后再次断言，防止 package/renderer 旁路把配置或 payload 写回 output。
  python3 quwoquan_ops/gate/verify_output_layout.py
  command -v dart >/dev/null 2>&1 || { echo "[gate] FAIL: dart not found in PATH" 1>&2; exit 1; }
  dart quwoquan_ops/tools/runtime_error_codegen/bin/generate_runtime_errors.dart --check
  dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart
  (cd quwoquan_service && make gate)
  (
    cd quwoquan_service/services/product-ops-service
    export QWQ_OUTPUT_ROOT="$ROOT/.qwq_output"
    # Intentionally unquoted: bash word-splits package paths from go list.
    # shellcheck disable=SC2046
    go test ./cmd/api \
      $(go list ./tests/... | grep -v '/tests/api_integration' || true) \
      -count=1
  )
}

run_app() {
  echo "[gate] quwoquan_app"
  local app_gate_phase="${QWQ_APP_GATE_PHASE:-all}"
  case "$app_gate_phase" in
    all|static|tests) ;;
    *)
      echo "[gate] FAIL: invalid QWQ_APP_GATE_PHASE: $app_gate_phase (expected all|static|tests)" >&2
      return 2
      ;;
  esac
  command -v flutter >/dev/null 2>&1 || { echo "[gate] FAIL: flutter not found in PATH" 1>&2; exit 1; }
  command -v dart >/dev/null 2>&1 || { echo "[gate] FAIL: dart not found in PATH" 1>&2; exit 1; }
  if [[ "$app_gate_phase" != "tests" ]]; then
    dart quwoquan_ops/tools/runtime_error_codegen/bin/generate_runtime_errors.dart --check
    dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart
    (cd quwoquan_app && flutter pub get --offline)
    # 仅分析主 App 业务代码与测试；vendor/plugins/** 属于 path overrides 的第三方依赖，
    # 其 example/test/pigeons 不应作为 quwoquan_app 主工程门禁输入。
    (cd quwoquan_app && flutter analyze lib test)
    # Dart 语义门禁：视觉 token + iOS 语义风格（chevron / Cupertino 组件边界）
    if command -v python3 >/dev/null 2>&1; then
    python3 quwoquan_app/scripts/runtime/verify_retired_terms_zero.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_concept_naming.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_cloud_tag_strict_typing.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_dart_semantic.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_unified_error_semantics_ratchet.py || exit 1
    python3 quwoquan_app/scripts/settings/verify_settings_canonical.py || exit 1
    python3 quwoquan_app/scripts/chat/verify_conversation_sheet_canonical.py || exit 1
    python3 quwoquan_app/scripts/chat/verify_chat_mock_remote_parity.py || exit 1
    python3 quwoquan_app/scripts/chat/verify_chat_group_roster_consistency.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_error_code_semantic.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_error_code_endcloud_parity.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_domain_error_code_registry.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_behavior_error_stack_convergence.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_cloud_services_semantic.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_app_remote_config_contract.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_ops_event_schema_completeness.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_route_and_context_semantic.py || exit 1
    python3 quwoquan_app/scripts/env/verify_runtime_host_literals.py || exit 1
    python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_no_personal_assistant_imports.py || exit 1
    python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_assistant_old_stack_retired.py || exit 1
    # L0 PA 降级响应契约静态分析（阻断）：
    #   - degraded:true 必须有 errorCode
    #   - finalText 不得泄漏 JSON envelope key
    #   - catch 块必须保留 $error 根因信息
    #   - spec 中的验收锚点与测试 spec_ref 必须双向有效
    python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_degraded_response_contract.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_ios_native_surface_gate.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_native_edge_navigation.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_page_object_contract.py || exit 1
    # 页面 A/B/C：默认 --quiet 仅汇总；GATE_PAGE_ABC_ENFORCE 选择阻断维度。
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
    # 助手手写 + App 搜索仓库：弱类型只减不增棘轮。
    python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_assistant_search_weak_typing_ratchet.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_user_profile_avatar_projection_versions.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_metadata_routes_vs_codegen_app.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_metadata_response_body_vs_codegen_app.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_cloud_security_cutovers.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_cloud_runtime_single_path.py || exit 1
    python3 quwoquan_app/scripts/auth/verify_auth_policy_contract.py || exit 1
    python3 quwoquan_app/scripts/auth/verify_login_entry_loop_contract.py || exit 1
    python3 quwoquan_app/scripts/device/verify_startup_ttid_baseline.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_startup_environment_matrix.py >/dev/null || exit 1
    python3 quwoquan_app/scripts/runtime/verify_plugin_registration_policy.py || exit 1
    python3 quwoquan_service/scripts/contract/verify_metadata_service_entities_vs_fields.py || exit 1
    python3 quwoquan_service/scripts/contract/verify_assistant_context_contract.py || exit 1
    python3 quwoquan_service/scripts/contract/verify_assistant_security_contract.py || exit 1
    python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py || exit 1
    python3 quwoquan_ops/gate/verify_media_delivery_contract.py || exit 1
    python3 quwoquan_ops/gate/verify_alpha_media_fixture_surface.py --files-only || exit 1
    python3 quwoquan_app/scripts/env/verify_contract_mock_data_inventory.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_app_no_integration_test_dir.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_lib_no_import_test_tree.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_remote_realtime_no_mock_import.py || exit 1
    python3 quwoquan_app/scripts/env/verify_ui_app_data_source_mode_ratchet.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_lib_no_test_only_symbols.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_lib_dart_io_budget.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_lib_platform_check_isolation.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_permission_coordinator_adoption.py || exit 1
    python3 quwoquan_app/scripts/runtime/verify_permission_primer_copy.py || exit 1
    python3 quwoquan_app/scripts/cli.py fonts verify || exit 1
    python3 quwoquan_app/scripts/cli.py web verify-offline || exit 1
    python3 quwoquan_app/scripts/env/verify_app_seed_manifests.py || exit 1
    python3 quwoquan_app/scripts/env/verify_business_env_data_inventory.py || exit 1
    python3 quwoquan_app/scripts/content/verify_markdown_article_no_article_document.py || exit 1
    python3 quwoquan_app/scripts/content/verify_article_contract_purity.py || exit 1
    python3 quwoquan_app/scripts/content/verify_post_view_projection_wire_keys.py || exit 1
    python3 quwoquan_app/scripts/content/verify_pageflip_backward_mainline.py || exit 1
    # content UI 目录归一不变量（R-CONTENTDIR-001/R-PAGEFLIP-002）：唯一 models 根 /
    # components/pageflip 引擎仅被 article_reader 宿主+test 消费 / article_render 渲染引擎不依赖 article_reader 宿主。
    python3 quwoquan_app/scripts/content/verify_content_ui_directory_boundaries.py || exit 1
    python3 quwoquan_ops/cli/gamma/verify_gamma_validation_profiles.py || exit 1
    python3 quwoquan_ops/ci/verify_ci_profile_consistency.py || exit 1
    # R03 文件行数预算（ratchet 只降不升，含 dart+go；pageflip 已登记豁免）
    python3 quwoquan_app/scripts/runtime/verify_file_line_budget.py || exit 1
    # R02 Repository 接口方法数预算（ratchet；伞组合接口免登记）
    python3 quwoquan_app/scripts/runtime/verify_repository_interface_method_budget.py || exit 1
    else
      echo "[gate] FAIL: python3 is required for App static verification" >&2
      exit 1
    fi
  fi
  if [[ "$app_gate_phase" == "static" ]]; then
    return 0
  fi
  # local_contract tests — fast, no external deps. Canonical App entry is test/local_contract/.
  # 使用 tee 边跑边输出：原先整段输出进变量，长时间无日志易被误判为「卡住」。
  # CI 在独立 runner 上按目录分片，但本地 `--scope app` 仍默认一次跑完整目录；
  # 分片不改变测试全集，也不放宽每个分片内部的 concurrency=1 契约。
  local app_test_shard="${QWQ_APP_TEST_SHARD:-all}"
  local run_pa_core="true"
  local -a flutter_test_targets
  case "$app_test_shard" in
    all)
      flutter_test_targets=("test/local_contract/")
      ;;
    ui)
      flutter_test_targets=("test/local_contract/ui/")
      run_pa_core="false"
      ;;
    runtime)
      flutter_test_targets=(
        "test/local_contract/app/"
        "test/local_contract/cloud/"
        "test/local_contract/core/"
        "test/local_contract/quality/"
      )
      ;;
    *)
      echo "[gate] FAIL: invalid QWQ_APP_TEST_SHARD: $app_test_shard (expected all|ui|runtime)" >&2
      return 2
      ;;
  esac
  local flutter_log
  flutter_log="$(mktemp -t quwoquan_gate_flutter_l1.XXXXXX)"
  local flutter_status=0
  set +e
  set -o pipefail
  python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py "${flutter_test_targets[@]}" 2>&1 | tee "$flutter_log"
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
  if [[ "$run_pa_core" == "true" ]]; then
    # PA Core（桶 A 协议契约 + 桶 B 引擎集成 + 桶 C UI 契约）默认全部阻断。
    # 桶 A 覆盖降级响应根因/消息记录协议/可观测字段，失败即退。
    bash quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/run_pa_core_tests.sh
  fi
  # Skip in CI: test/user_acceptance/patrol/ (needs real device/Patrol, run via FTL).

}

run_portal() {
  echo "[gate] ops-portal"
  command -v npm >/dev/null 2>&1 || { echo "[gate] FAIL: npm not found in PATH" 1>&2; exit 1; }
  local portal_dir="quwoquan_ops/portal"
  if [[ ! -f "$portal_dir/package-lock.json" ]]; then
    echo "[gate] FAIL: $portal_dir/package-lock.json missing — Portal dependencies must be locked in the Portal domain" 1>&2
    exit 1
  fi
  npm --prefix "$portal_dir" ci
  npm --prefix "$portal_dir" test
  npm --prefix "$portal_dir" run build
  rm -rf "$portal_dir/dist" "$portal_dir/.test-dist"
  rm -f "$portal_dir"/*.tsbuildinfo "$portal_dir"/vite.config.js "$portal_dir"/vite.config.d.ts
}

run_data() {
  echo "[gate] quwoquan_data"
  python3 quwoquan_data/scripts/cli.py verify all
}

echo "[gate] repo quality gate (scope=$scope)"

run_patrol_local() {
  # user_acceptance Patrol（本地调试用，CI 由 FTL workflow 承载）
  if ! command -v patrol >/dev/null 2>&1; then
    echo "[gate] SKIP: patrol CLI not found — user_acceptance patrol skipped (install: dart pub global activate patrol_cli)"
    return 0
  fi
  echo "[gate] user_acceptance Patrol (local device)"
  (cd quwoquan_app && patrol test test/user_acceptance/patrol/ --dart-define=RUN_T4_PATROL=true --dart-define=APP_RUNTIME_ENV=gamma --dart-define=API_CONTRACT_ENV=gamma)
}

case "$scope" in
  all)
    run_service
    run_data
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
  data)
    run_data
    ;;
  patrol)
    run_patrol_local
    ;;
  *)
    echo "[gate] FAIL: invalid scope: $scope (expected all|service|app|portal|data|patrol)" 1>&2
    exit 2
    ;;
esac

echo "[gate] OK"
