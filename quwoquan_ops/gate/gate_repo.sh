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

run_vertical_architecture_ratchet() {
  local vertical_scope="$1"
  echo "[gate] vertical architecture static ratchet (scope=$vertical_scope)"
  python3 quwoquan_ops/gate/verify_vertical_architecture_ratchet.py --scope "$vertical_scope"
}

run_vertical_architecture_local_contract() {
  echo "[gate] travel migration and vertical architecture local_contract"
  make test-vertical-architecture-ratchet-local-contract
}

case "$scope" in
  all|service|app)
    # 纯静态棘轮前置，先于构建与测试快速阻断垂类架构回退。
    run_vertical_architecture_ratchet "$scope"
    ;;
esac

if [ -d "$ROOT/scripts" ]; then
  echo "[gate] FAIL: root scripts/ directory must not exist — scripts belong in quwoquan_app/scripts/, quwoquan_service/scripts/, quwoquan_data/scripts/, or quwoquan_ops/" >&2
  exit 1
fi

bash quwoquan_ops/gate/scaffold/verify_global_increment_constraints.sh
python3 quwoquan_ops/gate/verify_git_branch_policy.py
python3 quwoquan_ops/gate/verify_github_supply_chain.py
python3 quwoquan_ops/gate/verify_agent_context_budget.py
python3 quwoquan_ops/gate/verify_retired_runtime_architecture.py
python3 quwoquan_ops/gate/verify_single_track_contracts.py
# 单轨契约合约测试：Python 1000 行硬顶治理后按场景拆分，随门禁一起执行。
python3 quwoquan_ops/tests/local_contract/gate/test_single_track_contracts__contract__local_contract_test.py
python3 quwoquan_ops/tests/local_contract/gate/test_single_track_contracts__versioned_identity__local_contract_test.py
python3 quwoquan_ops/tests/local_contract/gate/test_single_track_contracts__custom_control_documents__local_contract_test.py
python3 quwoquan_ops/tests/local_contract/gate/test_single_track_contracts__wire_and_alias__local_contract_test.py
python3 quwoquan_ops/gate/verify_ci_cd_evidence_contracts.py
python3 quwoquan_ops/gate/verify_behavior_event_type_contract.py
python3 quwoquan_ops/gate/verify_object_relation_edge_type_contract.py
python3 quwoquan_ops/gate/verify_homepage_type_contract.py
python3 quwoquan_ops/gate/verify_tag_collection_wiring.py
python3 quwoquan_ops/gate/verify_object_idempotency_dedup.py
python3 quwoquan_data/scripts/cli.py governance taxonomy closure-scorecard --gate
python3 quwoquan_ops/cli/cloud_contract_handoff.py verify
python3 quwoquan_app/scripts/runtime/codegen/verify_app_generated_manifest.py
python3 quwoquan_app/scripts/runtime/error/verify_app_recoverable_error_surface.py
python3 quwoquan_app/scripts/runtime/cloud/verify_cloud_package_boundaries.py
python3 quwoquan_ops/cli/feature_tree.py verify
python3 quwoquan_ops/gate/verify_execution_profiles.py
python3 quwoquan_ops/gate/scaffold/verify_test_directory_layout.py
python3 quwoquan_ops/gate/scaffold/verify_test_no_fake.py
# 对象 × 层 × UAT/DOM/SIT/GWT 的测试绑定闭合（make verify-test-coverage-map 同源）。
python3 quwoquan_ops/gate/scaffold/verify_test_coverage_map.py
# 四质量轴（a11y/observability/performance/reliability/visual）标签覆盖只增不减。
# 只挂在 make verify-test-nonfunctional-coverage 上时，主门禁链跑不到它，轴覆盖
# 下滑不会被任何一次提交拦住。
python3 quwoquan_ops/gate/scaffold/verify_quality_axis_coverage.py
# 棘轮基线自身的治理留痕：换度量口径必须同批记录旧口径与旧口径实测值，
# 否则漂移可以靠重建基线无痕销账。
python3 quwoquan_ops/gate/verify_ratchet_baseline_governance.py
python3 quwoquan_ops/gate/verify_local_dependency_purity.py
python3 quwoquan_ops/gate/verify_observability_layout.py
python3 quwoquan_ops/gate/verify_observability_envelope.py
# 监控配置面与代码 emit 面同源：幽灵指标、阈值漂移、scrape 拓扑漂移、
# 看板契约、手写 PromQL 未收敛，任一命中即 BLOCK（Delivery Gate 同链）。
python3 quwoquan_ops/gate/verify_metric_emitter_existence.py
python3 quwoquan_ops/gate/verify_metric_threshold_homology.py
python3 quwoquan_ops/gate/verify_prometheus_scrape_homology.py
python3 quwoquan_ops/gate/verify_grafana_dashboard_lint.py
python3 quwoquan_ops/gate/verify_contract_alert_overlay.py
python3 quwoquan_app/scripts/runtime/observability/verify_content_page_funnel_coverage.py
python3 quwoquan_ops/tests/local_contract/observability/test_content_page_funnel_coverage__observability__local_contract_test.py
python3 quwoquan_ops/gate/verify_runtime_log_governance.py
python3 quwoquan_ops/gate/verify_output_layout.py
python3 quwoquan_ops/gate/verify_output_path_source_contract.py
python3 quwoquan_ops/tests/local_contract/gate/test_output_path_source_contract__generated_artifact__local_contract_test.py
python3 quwoquan_ops/gate/verify_external_provider_governance.py
# 云侧环境在构建期绑定；六类镜像和入口必须校验内嵌 identity，Prod 不携带跨环境 facts。
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 quwoquan_ops/gate/verify_cloud_environment_artifact_binding.py
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 quwoquan_ops/tests/local_contract/gate/test_cloud_environment_artifact_binding__gate__local_contract_test.py
# Prod 选中绑定与服务 prod config 不得触达非生产 substitute 适配器。
python3 quwoquan_ops/gate/verify_provider_substitute_prod_purity.py
python3 quwoquan_ops/gate/verify_provider_conformance_evidence.py
python3 quwoquan_ops/gate/verify_entrypoint_script_paths.py
python3 quwoquan_ops/gate/verify_github_artifact_lifecycle.py
python3 -B quwoquan_ops/gate/verify_python_script_governance.py --scope all --mode check
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -B quwoquan_ops/tests/local_contract/gate/test_python_script_governance__derivation__local_contract_test.py
python3 quwoquan_ops/gate/verify_markdown_local_links.py
# 丢弃误写入源码树的 Python 缓存，再跑 root layout（缓存只允许落在 .qwq_output）。
find "$ROOT" \
  \( -path "$ROOT/.git" -o -path "$ROOT/.qwq_output" \) -prune -o \
  \( -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -exec rm -rf {} + \)
rm -rf "$ROOT/.pytest_cache"
python3 quwoquan_ops/gate/verify_root_layout.py
python3 quwoquan_app/scripts/runtime/architecture/verify_app_layout.py

run_service() {
  echo "[gate] quwoquan_service"
  # migration 控制面与架构棘轮单测只在 service/all 跑一次；app scope 仅跑前置静态扫描。
  run_vertical_architecture_local_contract
  python3 quwoquan_ops/cli/feature_tree.py verify
  python3 quwoquan_ops/gate/verify_stackctl_args_contract.py
  python3 quwoquan_ops/gate/verify_stackctl_provider_readiness_contract.py
python3 quwoquan_ops/gate/verify_dev_up_cli_surface.py
python3 quwoquan_ops/gate/verify_api_path_unversioned.py
python3 quwoquan_ops/gate/verify_environment_assembly.py
python3 quwoquan_ops/gate/verify_domain_governance.py
PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_test_data_architecture.py
# api_integration 直插存储只允许显式 persistence 专项；一般用例存量棘轮只减不增。
python3 quwoquan_ops/gate/verify_api_integration_direct_storage.py
# 正向错误码治理维度：契约声明的错误码必须有测试断言证据；
# 每服务缺失数棘轮只减不增，新错误码必须带断言测试。
python3 quwoquan_ops/gate/verify_error_code_assertion_coverage.py
# 反向错误码治理维度：实现发射但契约无声明位。存量走显式基线（只减不增），
# 新增未声明码与新增解析盲点 BLOCK；当前只覆盖 runtime NewCode 家族一种发射形态。
python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py
python3 quwoquan_ops/tests/local_contract/gate/test_emitted_error_code_declaration__contract__local_contract_test.py
  # 门禁自证：挂在 gate 链上的门禁，其配套 local_contract 测试必须也被 gate 链执行；
  # 否则门禁实现回退无人可见。缺口容忍基线已删除，本门禁为零容忍——配套测试统一由
  # make test-gate-companion-local-contract 执行。
  make test-gate-companion-local-contract
  python3 quwoquan_ops/gate/verify_gate_local_contract_execution.py
  python3 quwoquan_ops/tests/local_contract/gate/test_gate_local_contract_execution__contract__local_contract_test.py
  python3 quwoquan_ops/gate/verify_local_env_port_manifest.py
  python3 quwoquan_ops/gate/verify_prod_rollout_stackctl_contract.py
  python3 quwoquan_ops/tests/local_contract/environment/test_config_ack_governed_workload__local_contract_test.py
  python3 quwoquan_ops/gate/verify_prod_plane_access_isolation.py
  python3 quwoquan_ops/gate/verify_prod_access_guard.py
  bash quwoquan_service/scripts/verify/contract_graph/verify_contract_metadata.sh
  python3 quwoquan_service/scripts/verify/consistency/verify_tag_ref_source_of_truth.py
  # 内容域评论计数自洽（缺口A 防回归）：真相源 + 派生产物（*.lite.json / *.gamma-curated.json）
  # 的 commentCount/replyCount 不得与裁剪后评论集漂移。
  bash quwoquan_ops/environments/verify/verify_service_domain_layout.sh
  bash quwoquan_service/scripts/runtime/packaging/verify_runtime_packaging.sh
  bash quwoquan_ops/environments/verify/verify_ff_config_contract.sh
  python3 quwoquan_ops/gate/verify_service_architecture.py
  python3 quwoquan_service/scripts/runtime/reliabletask/verify_reliable_task_catalog.py
  python3 quwoquan_service/scripts/runtime/reliabletask/verify_reliable_task_retention_policy.py
  python3 quwoquan_service/scripts/runtime/packaging/verify_module_permission_scope.py
  python3 quwoquan_service/scripts/runtime/reliabletask/verify_reliable_task_migration.py
  # topology 由 delivery-gate topology job / make gate 负责，避免重复
  bash quwoquan_ops/environments/verify/verify_deploy_kustomization.sh
  bash quwoquan_service/scripts/recommendation-service/verify_recommendation_service_contract.sh
  python3 quwoquan_service/scripts/content-service/content/post/verify_daily_metrics_dimension_consistency.py
  # 推荐 policy 单轨守卫：禁止环境变体，gamma release 只绑定 canonical 内容摘要。
  python3 quwoquan_ops/gate/verify_canonical_recommendation_policy.py
  bash quwoquan_ops/environments/verify/verify_gray_rollout_stages.sh
  # 灰度路由策略（版本/userId/省份/运营商四维）schema 与枚举
  python3 quwoquan_ops/environments/verify/verify_gray_routing_policy.py
  # Config release guardrails (skeleton; strict mode via QWQ_CONFIG_GATE_STRICT=1)
  bash quwoquan_service/scripts/runtime/packaging/verify_service_config_layout.sh
  python3 quwoquan_ops/gate/verify_runtime_config_release_layout.py
  bash quwoquan_service/scripts/runtime/packaging/verify_service_env_contract.sh
  python3 quwoquan_service/scripts/user-service/verify_login_dependency_config.py
  python3 quwoquan_service/scripts/verify/consistency/verify_relationship_error_code_gate.py
  python3 quwoquan_service/scripts/verify/consistency/verify_error_recovery_alignment.py
  # 阶段名标识零容忍：稳定可执行路径、schema key 与测试标识禁止 m2/b10/phase0/partN。
  python3 quwoquan_service/scripts/verify/structure/verify_stage_name_identifiers.py
  # nil 语义：wire 边界禁止值类型 bool+omitempty（false 会消失）；端口层空返回棘轮。
  python3 quwoquan_service/scripts/verify/structure/verify_nil_semantics.py
  python3 quwoquan_ops/tests/local_contract/observability/test_object_alert_coverage__contract_graph_mapping__observability__local_contract_test.py
  python3 quwoquan_service/scripts/verify/observability/verify_object_alert_coverage.py
  # 告警表达式求值回归（promtool test rules）：云侧交付面必须证明关键告警
  # 在注入序列下按预期开火/保持安静；CI service runner 安装 prometheus 提供 promtool。
  command -v promtool >/dev/null 2>&1 || {
    echo "[gate] FAIL: promtool is required for alert rule evaluation (install prometheus)"
    exit 1
  }
  promtool test rules "$ROOT"/quwoquan_ops/observability/monitoring/promtool_tests/*.yaml
  # 对象 × 层的结构性证据闭合：由受管管线现场派生 ContractGraph，
  # 任何 STRUCTURAL 缺口直接 BLOCK；不存在债务基线、刷新入口或计数额度。
  # 合约测试在 Python 1000 行硬顶治理后按场景拆分，全部随门禁一起执行。
  python3 quwoquan_ops/tests/local_contract/gate/test_object_evidence_closure__strict_zero__contract_graph__local_contract_test.py
  python3 quwoquan_ops/tests/local_contract/gate/test_object_evidence_closure__strict_zero__structural_policy__local_contract_test.py
  python3 quwoquan_ops/tests/local_contract/gate/test_object_evidence_closure__strict_zero__dynamic_readiness__local_contract_test.py
  python3 quwoquan_ops/tests/local_contract/gate/test_object_evidence_closure__strict_zero__artifact_blindspot__local_contract_test.py
  python3 quwoquan_ops/tests/local_contract/gate/test_object_evidence_closure__strict_zero__page_consumption__local_contract_test.py
  python3 quwoquan_ops/gate/verify_object_evidence_closure.py
  # 对象开放面 fail-closed 契约闭合：搜索开放、小趣开放与 ES 字段漂移。
  # 三者均为 strict-zero，无基线、无 allowlist。
  python3 quwoquan_ops/gate/verify_object_search_policy_closure.py
  python3 quwoquan_ops/gate/verify_object_assistant_access_closure.py
  python3 quwoquan_ops/gate/verify_search_index_field_drift.py
  # 搜索请求过滤词汇单轨：App enum / GraphQL schema / api-edge 映射 /
  # search-service 校验四处同源，防止 objectTypes 词汇断链回归。
  python3 quwoquan_ops/gate/verify_search_wire_vocabulary_single_track.py
  # UAT 与 ops 层测试义务反向派生：磁盘验收测试必须有契约 readiness case，
  # 存量缺口按棘轮基线只减不增；UA 声明的 runner 路径 strict-zero。
  python3 quwoquan_ops/gate/verify_readiness_case_coverage.py
  python3 quwoquan_service/scripts/entity-service/entity_homepage/homepage/verify_entity_homepage_object_mainline.py
  python3 quwoquan_app/scripts/env/verify_public_vs_upstream_url_contract.py
  bash quwoquan_ops/environments/verify/verify_service_config_digest_mapping.sh
  bash quwoquan_ops/environments/verify/verify_image_identity_single_track.sh
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
  # 云侧 statement 覆盖率按 service/context/object 计量；service cmd 与仓库级
  # shared runtime 分别进入显式 cross-cutting 单元。旧格式输入直接 fail-closed，
  # 只有唯一 canonical receipt/rule/baseline 能参与 Delivery Gate。
  python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --scope cloud
}

run_app() {
  echo "[gate] quwoquan_app"
  local app_phase="${GATE_APP_PHASE:-all}"
  case "$app_phase" in
    all|static|tests|serial) ;;
    *)
      echo "[gate] FAIL: invalid GATE_APP_PHASE=$app_phase (expected all|static|tests|serial)" >&2
      exit 2
      ;;
  esac
  command -v flutter >/dev/null 2>&1 || { echo "[gate] FAIL: flutter not found in PATH" 1>&2; exit 1; }
  command -v dart >/dev/null 2>&1 || { echo "[gate] FAIL: dart not found in PATH" 1>&2; exit 1; }

  if [[ "$app_phase" == "all" || "$app_phase" == "static" ]]; then
  python3 quwoquan_ops/gate/verify_app_architecture.py || exit 1
  python3 quwoquan_ops/gate/verify_app_client_contract_kind_alignment.py || exit 1
  dart quwoquan_ops/tools/runtime_error_codegen/bin/generate_runtime_errors.dart --check
  dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart
  (cd quwoquan_app && flutter pub get --offline)
  # 仅分析主 App 业务代码与测试；vendor/plugins/** 属于 path overrides 的第三方依赖，
  # 其 example/test/pigeons 不应作为 quwoquan_app 主工程门禁输入。
  (cd quwoquan_app && flutter analyze lib test)
  # Dart 语义门禁：视觉 token + iOS 语义风格（chevron / Cupertino 组件边界）
  if command -v python3 >/dev/null 2>&1; then
    python3 quwoquan_app/scripts/runtime/architecture/verify_retired_terms_zero.py || exit 1
    python3 quwoquan_app/scripts/runtime/architecture/verify_concept_naming.py || exit 1
    python3 quwoquan_app/scripts/tag_service/tag/verify_cloud_tag_strict_typing.py || exit 1
    python3 quwoquan_app/scripts/runtime/observability/verify_dart_semantic.py || exit 1
    python3 quwoquan_app/scripts/runtime/observability/verify_catch_swallow_budget.py || exit 1
    python3 quwoquan_app/scripts/runtime/observability/verify_null_failure_isolation.py || exit 1
    python3 quwoquan_app/scripts/runtime/observability/verify_theme_binding_ratchet.py || exit 1
    python3 quwoquan_app/scripts/runtime/observability/verify_journey_action_declaration_ratchet.py || exit 1
    python3 quwoquan_app/scripts/runtime/page/verify_component_reuse_ratchet.py || exit 1
    python3 quwoquan_app/scripts/runtime/error/verify_unified_error_semantics_ratchet.py || exit 1
    # App 侧生成错误码的测试断言覆盖棘轮：未断言码只减不增。
    python3 quwoquan_app/scripts/runtime/error/verify_app_error_code_assertion_coverage.py || exit 1
    python3 quwoquan_app/scripts/runtime/page/verify_settings_canonical.py || exit 1
    python3 quwoquan_app/scripts/runtime/page/verify_conversation_sheet_canonical.py || exit 1
    python3 quwoquan_app/scripts/chat_service/chat/verify_chat_group_roster_consistency.py || exit 1
    python3 quwoquan_app/scripts/runtime/error/verify_error_code_semantic.py || exit 1
    python3 quwoquan_app/scripts/runtime/error/verify_error_code_endcloud_parity.py || exit 1
    python3 quwoquan_app/scripts/runtime/error/verify_app_error_code_assertion_coverage.py || exit 1
    python3 quwoquan_app/scripts/runtime/error/verify_domain_error_code_registry.py || exit 1
    python3 quwoquan_app/scripts/runtime/error/verify_behavior_error_stack_convergence.py || exit 1
    python3 quwoquan_app/scripts/runtime/cloud/verify_cloud_services_semantic.py || exit 1
    python3 quwoquan_app/scripts/runtime/cloud/verify_app_remote_config_contract.py || exit 1
    python3 quwoquan_app/scripts/runtime/observability/verify_ops_event_schema_completeness.py || exit 1
    python3 quwoquan_app/scripts/runtime/page/verify_route_and_context_semantic.py || exit 1
    python3 quwoquan_app/scripts/runtime/page/verify_link_templates_route_ids.py || exit 1
    python3 quwoquan_app/scripts/env/verify_runtime_host_literals.py || exit 1
    python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_no_personal_assistant_imports.py || exit 1
    python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_assistant_old_stack_retired.py || exit 1
    # L0 PA 降级响应契约静态分析（阻断）：
    #   - degraded:true 必须有 errorCode
    #   - finalText 不得泄漏 JSON envelope key
    #   - catch 块必须保留 $error 根因信息
    #   - spec 中的验收锚点与测试 spec_ref 必须双向有效
    python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_degraded_response_contract.py || exit 1
    python3 quwoquan_app/scripts/runtime/page/verify_ios_native_surface_gate.py || exit 1
    python3 quwoquan_app/scripts/runtime/page/verify_native_edge_navigation.py || exit 1
    python3 quwoquan_app/scripts/runtime/page/verify_page_object_contract.py || exit 1
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
      python3 quwoquan_app/scripts/runtime/page/verify_page_abc_governance.py --quiet ${_abc_flags} || exit 1
    else
      python3 quwoquan_app/scripts/runtime/page/verify_page_abc_governance.py --quiet
    fi
    # 助手手写 + App 搜索仓库：弱类型只减不增棘轮。
    python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_assistant_search_weak_typing_ratchet.py || exit 1
    # 契约 enum_ref 必须以 typed Dart enum 抵达 App；口径来自 codegen 的字段绑定
    # 报告。此前它只挂在 Makefile 的 gate target 上，而 CI 只跑 gate_repo.sh，
    # 于是这道门从未在 CI 执行过，基线一路漂移无人拦截。
    python3 quwoquan_app/scripts/runtime/codegen/verify_app_enum_typed_binding.py || exit 1
    python3 quwoquan_app/scripts/user_service/account/user_account/verify_user_profile_avatar_projection_versions.py || exit 1
    python3 quwoquan_app/scripts/runtime/codegen/verify_metadata_routes_vs_codegen_app.py || exit 1
    python3 quwoquan_app/scripts/runtime/codegen/verify_metadata_response_body_vs_codegen_app.py || exit 1
    python3 quwoquan_app/scripts/runtime/cloud/verify_cloud_security_cutovers.py || exit 1
    python3 quwoquan_app/scripts/runtime/cloud/verify_cloud_runtime_single_path.py || exit 1
    python3 quwoquan_app/scripts/runtime/auth/verify_auth_policy_contract.py || exit 1
    python3 quwoquan_app/scripts/runtime/auth/verify_login_entry_loop_contract.py || exit 1
    # RTC 通话商用契约：铃声单轨、信令通道恢复补偿、动效 token、关键测试证据链。
    python3 quwoquan_app/scripts/rtc_service/rtc/call_session/verify_rtc_call_contract.py || exit 1
    python3 quwoquan_app/scripts/device/verify_startup_ttid_baseline.py || exit 1
    make verify-app-identity-state-isolation || exit 1
    make verify-app-identity || exit 1
    python3 quwoquan_app/scripts/runtime/platform/verify_startup_environment_matrix.py >/dev/null || exit 1
    python3 quwoquan_app/scripts/runtime/platform/verify_dual_platform_usability_baseline.py || exit 1
    python3 quwoquan_app/scripts/runtime/platform/verify_plugin_registration_policy.py || exit 1
    python3 quwoquan_service/scripts/verify/contract_graph/verify_metadata_service_entities_vs_fields.py || exit 1
    python3 quwoquan_service/scripts/assistant-service/assistant/assistant_run/verify_assistant_context_contract.py || exit 1
    python3 quwoquan_service/scripts/assistant-service/verify_assistant_security_contract.py || exit 1
    python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py || exit 1
    python3 quwoquan_app/scripts/env/verify_aggregate_mock_ratchet.py || exit 1
    python3 quwoquan_ops/gate/verify_media_delivery_contract.py || exit 1
    python3 quwoquan_app/scripts/runtime/architecture/verify_app_no_integration_test_dir.py || exit 1
    # 五域对象级 generated Remote api_integration 证据：ContractGraph 派生，
    # local_contract 锁 stackctl 接线与单调棘轮，再执行静态边界门禁。
    make verify-app-domain-remote-api-integration || exit 1
    python3 quwoquan_app/scripts/runtime/architecture/verify_lib_no_import_test_tree.py || exit 1
    python3 quwoquan_app/scripts/runtime/cloud/verify_remote_realtime_no_mock_import.py || exit 1
    python3 quwoquan_app/scripts/runtime/cloud/verify_production_data_source_single_path.py || exit 1
    python3 quwoquan_app/scripts/runtime/architecture/verify_lib_no_test_only_symbols.py || exit 1
    python3 quwoquan_app/scripts/runtime/platform/verify_lib_dart_io_budget.py || exit 1
    python3 quwoquan_app/scripts/runtime/platform/verify_lib_platform_check_isolation.py || exit 1
    python3 quwoquan_app/scripts/runtime/auth/verify_permission_coordinator_adoption.py || exit 1
    python3 quwoquan_app/scripts/runtime/auth/verify_permission_primer_copy.py || exit 1
    python3 quwoquan_app/scripts/cli.py fonts verify || exit 1
    python3 quwoquan_app/scripts/cli.py web verify-offline || exit 1
    python3 quwoquan_app/scripts/content_service/content/post/verify_markdown_article_no_article_document.py || exit 1
    python3 quwoquan_app/scripts/content_service/content/post/verify_article_contract_purity.py || exit 1
    python3 quwoquan_app/scripts/content_service/content/post/verify_post_view_projection_wire_keys.py || exit 1
    python3 quwoquan_app/scripts/content_service/content/verify_ui_content_no_dynamic_parameters.py || exit 1
    python3 quwoquan_app/scripts/content_service/verify_content_wire_dto_fields.py || exit 1
    python3 quwoquan_app/scripts/content_service/content/post/verify_pageflip_backward_mainline.py || exit 1
    # content UI 目录归一不变量（R-CONTENTDIR-001/R-PAGEFLIP-002）：唯一 models 根 /
    # components/pageflip 引擎仅被 article_reader 宿主+test 消费 / article_render 渲染引擎不依赖 article_reader 宿主。
    python3 quwoquan_app/scripts/content_service/verify_content_ui_directory_boundaries.py || exit 1
    python3 quwoquan_ops/cli/gamma/verify_gamma_validation_profiles.py || exit 1
    python3 quwoquan_ops/ci/verify_ci_profile_consistency.py || exit 1
    # R03 文件行数预算（ratchet 只降不升，含 dart+go；pageflip 已登记豁免）
    PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/tests/local_contract/gate/test_file_line_budget__source_roots__local_contract_test.py || exit 1
    python3 quwoquan_app/scripts/runtime/architecture/verify_file_line_budget.py || exit 1
    # R02 Repository 接口方法数预算（ratchet；伞组合接口免登记）
    python3 quwoquan_app/scripts/runtime/architecture/verify_repository_interface_method_budget.py || exit 1
    # UI 层 Map<String,dynamic> 字面量零容忍（存量已清零，命中即 FAIL）
    python3 quwoquan_app/scripts/runtime/page/verify_ui_map_literal_budget.py || exit 1
    # 性能预算聚合门禁：会话滚动/发送确认与 feed 查询 p95 超预算即阻断合入，
    # 与静态同相位执行，避免每个 tests shard 重复。
    # spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/message-runtime-performance-budget/spec.md#gwt-001.t2
    make verify-performance-budgets || exit 1
  else
    echo "[gate] FAIL: python3 is required for App static verification" >&2
    exit 1
  fi
  # PA Core 与静态同相位，避免每个 shard 重复。
  bash quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/run_pa_core_tests.sh
  fi

  if [[ "$app_phase" == "static" ]]; then
    echo "[gate] app phase=static OK"
    return 0
  fi

  if [[ "$app_phase" == "tests" || "$app_phase" == "serial" ]]; then
    (cd quwoquan_app && flutter pub get --offline)
  fi

  # 唯一 canonical coverage rule 的端侧行 + 分支计量。--collect 自带一次
  # `flutter test --coverage --branch-coverage test/local_contract` 采集，
  # 采集范围与基线登记的 scope 同源；产物落在 .qwq_output 的可删除缓存里。
  # 放在常规套件之后：套件红的时候先报套件本身的失败，别让覆盖率采集抢先。
  run_app_canonical_coverage() {
    python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --scope app
  }

  # 唯一 App Python local_contract runner；静态相位不执行测试，serial shard 也不
  # 重复执行，tests/all 各自只经 Makefile canonical target 进入一次。
  run_app_python_local_contract_tests() {
    make test-app-python-local-contract
  }

  # local_contract tests — Canonical App entry is test/local_contract/.
  # 使用 tee 边跑边输出：原先整段输出进变量，长时间无日志易被误判为「卡住」。
  run_app_flutter_tests() {
    local serial_mode="$1"
    local concurrency_env="${2:-}"
    local flutter_log
    flutter_log="$(mktemp -t quwoquan_gate_flutter_l1.XXXXXX)"
    local flutter_status=0
    set +e
    set -o pipefail
    FLUTTER_TEST_SERIAL_MODE="$serial_mode" \
    FLUTTER_TEST_CONCURRENCY="${concurrency_env:-4}" \
      python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/local_contract/ 2>&1 | tee "$flutter_log"
    flutter_status="${PIPESTATUS[0]}"
    set +o pipefail
    set -e
    if [[ -z "$flutter_status" ]]; then
      flutter_status=1
    fi
    if [[ "$flutter_status" -ne 0 ]]; then
      if grep -Fq "Connection closed before full header was received" "$flutter_log" 2>/dev/null; then
        echo ""
        echo "[gate] FAIL: flutter_tester loopback bootstrap failed — Proxifier Network Extension is intercepting 127.0.0.1 TCP connections."
        echo ""
        echo "[gate] FIX: add Proxifier Direct rule for 127.0.0.1 / ::1 / localhost, then re-run make gate"
        echo ""
      fi
      rm -f "$flutter_log"
      return 1
    fi
    rm -f "$flutter_log"
    return 0
  }

  if [[ "$app_phase" == "serial" ]]; then
    # serial 分片只跑隔离子集，覆盖率不具代表性；棘轮由 tests / all 相位承担。
    FLUTTER_TEST_GUARD_TIMEOUT_SECONDS="${FLUTTER_TEST_GUARD_TIMEOUT_SECONDS:-1800}" \
      run_app_flutter_tests "only" "1" || return 1
    echo "[gate] app phase=serial OK"
    return 0
  fi

  if [[ "$app_phase" == "tests" ]]; then
    FLUTTER_TEST_GUARD_TIMEOUT_SECONDS="${FLUTTER_TEST_GUARD_TIMEOUT_SECONDS:-1800}" \
      run_app_flutter_tests "${FLUTTER_TEST_SERIAL_MODE:-exclude}" "${FLUTTER_TEST_CONCURRENCY:-8}" || return 1
    run_app_python_local_contract_tests || return 1
    run_app_canonical_coverage
    echo "[gate] app phase=tests OK"
    return 0
  fi

  # app_phase=all：并行套件 + 串行隔离套件各跑一次（仍非双跑全量）。
  FLUTTER_TEST_GUARD_TIMEOUT_SECONDS="${FLUTTER_TEST_GUARD_TIMEOUT_SECONDS:-1200}" \
    run_app_flutter_tests "exclude" "${FLUTTER_TEST_CONCURRENCY:-4}" || return 1
  FLUTTER_TEST_GUARD_TIMEOUT_SECONDS="${FLUTTER_TEST_GUARD_TIMEOUT_SECONDS:-1800}" \
    run_app_flutter_tests "only" "1" || return 1
  run_app_python_local_contract_tests || return 1
  run_app_canonical_coverage
  # Skip in CI: canonical Patrol-tagged user_acceptance targets need a real device
  # and run via the dedicated Patrol/FTL scope below.

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
  local candidate patrol_target_output
  local -a patrol_targets=()
  if ! patrol_target_output="$(
    python3 quwoquan_ops/gate/scaffold/verify_test_directory_layout.py \
      --list-patrol-user-acceptance-targets
  )"; then
    echo "[gate] FAIL: could not enumerate canonical Patrol targets" >&2
    return 1
  fi
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] && patrol_targets+=("${candidate#quwoquan_app/}")
  done <<<"$patrol_target_output"
  if (( ${#patrol_targets[@]} == 0 )); then
    echo "[gate] FAIL: no canonical user_acceptance Patrol targets found" >&2
    return 1
  fi
  echo "[gate] user_acceptance Patrol (local device, targets=${#patrol_targets[@]})"
  local target
  local -a patrol_args=()
  for target in "${patrol_targets[@]}"; do
    echo "[gate] patrol target: $target"
    patrol_args+=(--target "$target")
  done
  (
    cd quwoquan_app
    patrol test "${patrol_args[@]}" \
      --dart-define=RUN_PATROL_ACCEPTANCE=true \
      --dart-define=APP_RUNTIME_ENV=gamma \
      --dart-define=API_CONTRACT_ENV=gamma
  )
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
