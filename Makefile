.PHONY: gate
.PHONY: gate-local-gamma
.PHONY: gate-runtime-media
.PHONY: gate-runtime-media-full
.PHONY: verify-chat-avatar-commercial-matrix
.PHONY: verify-app-mock-isolation
.PHONY: verify-api-path-unversioned
.PHONY: verify-api-path-runtime
.PHONY: verify-app-runtime-host-literals
.PHONY: verify-app-concept-naming
.PHONY: verify-app-auth-policy
.PHONY: verify-app-domain-error-code-registry
.PHONY: verify-app-behavior-error-stack-convergence
.PHONY: verify-app-permission-coordinator-adoption
.PHONY: verify-app-permission-primer-copy
.PHONY: verify-app-startup-ttid
.PHONY: verify-app-startup-environment-pr
.PHONY: verify-app-startup-environment-uat
.PHONY: verify-app-startup-observability-release
.PHONY: verify-app-experience-observability
.PHONY: verify-app-recoverable-error-surface
.PHONY: verify-app-dual-platform-usability-baseline
.PHONY: verify-app-ios-hot-restart
.PHONY: build-app-startup-environment-matrix
.PHONY: verify-app-lib-no-test-import
.PHONY: verify-app-page-horizontal-quality
.PHONY: verify-app-page-object-contract
.PHONY: verify-app-content-ui-boundaries
.PHONY: verify-app-remote-config-contract
.PHONY: verify-app-native-edge-navigation
.PHONY: verify-app-pageflip-backward-static
.PHONY: verify-app-pageflip-backward-tests
.PHONY: verify-app-pageflip-back-mainline
.PHONY: verify-quality-axis-coverage test-coverage-heatmap verify-performance-budgets verify-alert-drill-closure
.PHONY: verify-ratchet-baseline-governance
.PHONY: verify-app-page-abc-governance
.PHONY: verify-app-page-abc-governance-enforce-a
.PHONY: verify-app-page-abc-governance-enforce-b
.PHONY: verify-app-page-abc-governance-enforce-c
.PHONY: verify-app-page-abc-governance-enforce-all
.PHONY: verify-app-ui-map-literal-budget
.PHONY: verify-app-assistant-search-weak-typing-ratchet
.PHONY: verify-app-assistant-old-stack-retired
.PHONY: verify-assistant-agent-replay-evaluation
.PHONY: verify-retired-terms-zero
.PHONY: verify-app-production-data-source-single-path
.PHONY: verify-production-wiring-purity
.PHONY: verify-provider-substitute-prod-purity
.PHONY: verify-test-data-architecture
.PHONY: verify-test-data-environment-results
.PHONY: verify-test-data-performance
.PHONY: fetch-app-bundled-fonts
.PHONY: verify-app-bundled-fonts
.PHONY: check-app-bundled-fonts-updates
.PHONY: verify-app-web-offline-resources
.PHONY: verify-quwoquan-data
.PHONY: verify-markdown-article-no-article-document verify-article-contract-purity
.PHONY: verify-app-env-package
.PHONY: verify-service-env-package
.PHONY: verify-env-topology verify-prod-plane-access-isolation
.PHONY: verify-local-port-manifest
.PHONY: verify-public-vs-upstream-url-contract
.PHONY: verify-domain-governance
.PHONY: verify-python-script-governance
.PHONY: verify-vertical-architecture-ratchet
.PHONY: test-vertical-architecture-ratchet-local-contract
.PHONY: sync-page-object-source-paths verify-page-object-source-paths
.PHONY: verify-gamma-local-prod-isomorphism
.PHONY: verify-app-aggregate-mock-ratchet verify-api-integration-direct-storage verify-environment-stability-final-acceptance
.PHONY: verify-github-artifact-lifecycle
.PHONY: verify-emitted-error-code-declaration
.PHONY: verify-login-dependency-config
.PHONY: verify-env-packaging
.PHONY: verify-env-instance-isolation
.PHONY: observability-es-up
.PHONY: observability-es-down
.PHONY: observability-es-health
.PHONY: observability-es-bootstrap
.PHONY: observability-es-smoke
.PHONY: observability-alert-drill
.PHONY: verify-reliable-task-topology
.PHONY: verify-service-architecture
.PHONY: verify-canonical-coverage
.PHONY: verify-canonical-coverage-app
.PHONY: verify-canonical-coverage-service
.PHONY: write-canonical-coverage-baseline
.PHONY: verify-metadata
.PHONY: verify-append-only-fact-command-admission
.PHONY: verify-contract-alert-overlay
.PHONY: verify-metric-identity-homology
.PHONY: verify-metric-threshold-homology
.PHONY: verify-prometheus-scrape-homology
.PHONY: verify-grafana-dashboard-lint
.PHONY: verify-metric-emitter-existence
.PHONY: verify-prometheus-rule-tests
.PHONY: verify-page-telemetry-coverage
.PHONY: verify-operation-privacy-redaction
.PHONY: build-app-env
.PHONY: build-service-env
.PHONY: beta-up
.PHONY: beta-down
.PHONY: beta-status
.PHONY: verify
.PHONY: verify-global-increment-constraints
.PHONY: verify-agent-context-contract
.PHONY: verify-retired-runtime-architecture
.PHONY: verify-service-ddd-cqrs-baseline
.PHONY: verify-commercial-contract-generation
.PHONY: verify-behavior-event-type-contract
.PHONY: verify-object-relation-edge-type-contract
.PHONY: verify-object-alert-coverage
.PHONY: verify-object-evidence-closure verify-object-evidence-commercial-closure
.PHONY: verify-readiness-execution-plan collect-readiness-result-bundle
.PHONY: verify-app-domain-remote-api-integration
.PHONY: verify-homepage-type-contract
.PHONY: verify-app-cloud-runtime-single-path
.PHONY: verify-app-cloud-security-cutovers
.PHONY: accept-app-contract-handoff
.PHONY: accept-app-contract-handoff-atomic
.PHONY: verify-app-contract-handoff
.PHONY: verify-app-contract-handoff-inputs
.PHONY: verify-app-generated-manifest
.PHONY: verify-graphql-app-client
.PHONY: verify-app-enum-typed-binding
.PHONY: verify-app-cohesion-ratchet
.PHONY: verify-app-shell-navigation
.PHONY: verify-app-cloud-package-boundaries
.PHONY: codegen
.PHONY: codegen-observability-catalog
.PHONY: verify-observability-catalog
.PHONY: verify-runtime-log-governance
.PHONY: codegen-app
.PHONY: codegen-app-shell-navigation
.PHONY: codegen-ops-portal
.PHONY: codegen-control-plane-runtime
.PHONY: codegen-content-service
.PHONY: codegen-chat-service
.PHONY: new-service
.PHONY: config-slo-gate
.PHONY: stackctl-package
.PHONY: stackctl-verify
.PHONY: dev-session
.PHONY: stackctl-up
.PHONY: stackctl-down
.PHONY: stackctl-status

REPO_ROOT ?= $(CURDIR)
# Always pin to the repo output root. A polluted shell export (for example a
# leftover data-local-contract temp dir) must not redirect gate/stackctl output
# into disposable pytest isolation roots scanned by verify_test_no_fake.
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
export QWQ_OUTPUT_ROOT

QWQ_PYTHON_CACHE_ROOT ?= $(HOME)/.cache/quwoquan/python-envs
export QWQ_PYTHON_CACHE_ROOT
DATA_PYTHON ?= $(QWQ_PYTHON_CACHE_ROOT)/quwoquan-data/bin/python
PYTEST_RUNNER ?= $(DATA_PYTHON)
PYTEST_INTERPRETER_FLAGS ?= -B
PYTEST_FLAGS ?= -o cache_dir=$(QWQ_OUTPUT_ROOT)/env/repo/local/tests/cache/pytest
# Go 默认按所有逻辑 CPU 并发运行 package。大型聚合门禁中，每个 test
# binary 又拥有完整 GOMAXPROCS，容易让外部媒体探针在自身 deadline 前得不到
# 调度。统一限制 package 并发；隔离 runner 可显式覆盖，但不得另写测试入口。
GO_TEST_PACKAGE_PARALLELISM ?= 4
# API integration packages provision heavyweight shared local dependencies
# (Docker, MongoDB, Redis, PostgreSQL, MinIO). The local-env gate is serial by
# topology contract; keep package binaries serial too so readiness is evidence
# of the tested service rather than host scheduler/container contention.
API_INTEGRATION_GO_TEST_PACKAGE_PARALLELISM ?= 1
export PYTHONDONTWRITEBYTECODE := 1
export PYTHONPYCACHEPREFIX := $(QWQ_OUTPUT_ROOT)/env/repo/local/test-runtime/cache/bytecode/make
.PHONY: stackctl-health
.PHONY: stackctl-inspect
.PHONY: stackctl-doctor
.PHONY: stackctl-repair
.PHONY: stackctl-deploy

# 客户端：production lib、pubspec、Patrol/UAT 不得直连 Mock/fixture。
verify-app-mock-isolation:
	@python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py

# HTTP API path 禁止 /vN、/internal/vN、/callbacks/vN（已挂入 gate_repo.sh）
verify-api-path-unversioned:
	@python3 quwoquan_ops/gate/verify_api_path_unversioned.py

# 运行时新旧 path 探针（live；密钥/起栈就绪后执行，不强制进静态门禁）
# 例: make verify-api-path-runtime ENV=gamma
verify-api-path-runtime:
	@python3 quwoquan_ops/cli/probes/verify_api_path_runtime_unversioned.py --env $${ENV:-gamma}

verify-app-runtime-host-literals:
	@python3 quwoquan_app/scripts/env/verify_runtime_host_literals.py

verify-app-concept-naming:
	@python3 quwoquan_app/scripts/runtime/architecture/verify_concept_naming.py

# 端云错误码全集一致：云 errors.yaml code 集 == 客户端生成 *ErrorCode 枚举集
verify-app-error-endcloud-parity:
	@python3 quwoquan_app/scripts/runtime/error/verify_error_code_endcloud_parity.py

# App 侧 generated 错误码断言覆盖棘轮：未断言码数只减不增
verify-app-error-code-assertion-coverage:
	@python3 quwoquan_app/scripts/runtime/error/verify_app_error_code_assertion_coverage.py

verify-app-domain-error-code-registry:
	@python3 quwoquan_app/scripts/runtime/error/verify_domain_error_code_registry.py

verify-app-behavior-error-stack-convergence:
	@python3 quwoquan_app/scripts/runtime/error/verify_behavior_error_stack_convergence.py

# 业务 catch 吞错预算（空 catch / 仅本地打印）：棘轮基线只减不增
verify-app-catch-swallow-budget:
	@python3 quwoquan_app/scripts/runtime/observability/verify_catch_swallow_budget.py

# 空引用与失败隔离：catch 内 return null 必须是 try 前缀解析器或留有观测证据
verify-app-null-failure-isolation:
	@python3 quwoquan_app/scripts/runtime/observability/verify_null_failure_isolation.py

# 主题绑定门禁：业务层禁硬绑 AppColors.light/dark，isDark 三元只减不增
verify-app-theme-binding-ratchet:
	@python3 quwoquan_app/scripts/runtime/observability/verify_theme_binding_ratchet.py

# 埋点 journey/action 闭集棘轮：未声明字面量对/动态插值/存量 Analytics 只减不增
verify-app-journey-action-declaration:
	@python3 quwoquan_app/scripts/runtime/observability/verify_journey_action_declaration_ratchet.py

# 组件复用棘轮：页面私有空态/骨架轮子只减不增（空态统一 AppEmptyState）
verify-app-component-reuse-ratchet:
	@python3 quwoquan_app/scripts/runtime/page/verify_component_reuse_ratchet.py

# recovery 对齐：errors.yaml recovery_action -> 生成 Go .WithRecovery（factory 风格域）
verify-service-error-recovery-alignment:
	@python3 quwoquan_service/scripts/verify/consistency/verify_error_recovery_alignment.py

# nil 语义：wire 边界禁止值类型 bool+omitempty；领域端口空返回兼作未命中信号只减不增
verify-service-nil-semantics:
	@python3 quwoquan_service/scripts/verify/structure/verify_nil_semantics.py

# API 鉴权契约：security.auth_mode 真相源与端侧鉴权快照一致，核心受限入口必须 required
verify-app-auth-policy:
	@python3 quwoquan_app/scripts/runtime/auth/verify_auth_policy_contract.py

verify-app-login-entry-loop-contract:
	@python3 quwoquan_app/scripts/runtime/auth/verify_login_entry_loop_contract.py

# RTC 通话商用契约：铃声单一真相源、信令通道恢复补偿、动效 token 与关键测试证据链
verify-app-rtc-call-contract:
	@python3 quwoquan_app/scripts/rtc_service/rtc/call_session/verify_rtc_call_contract.py

verify-app-permission-coordinator-adoption:
	@python3 quwoquan_app/scripts/runtime/auth/verify_permission_coordinator_adoption.py

verify-app-permission-primer-copy:
	@python3 quwoquan_app/scripts/runtime/auth/verify_permission_primer_copy.py

verify-app-startup-ttid:
	@python3 quwoquan_ops/gate/verify_python_syntax.py \
		quwoquan_app/scripts/device/verify_startup_first_frame.py \
		quwoquan_app/scripts/device/verify_startup_ttid_baseline.py \
		quwoquan_app/scripts/device/verify_startup_web.py \
		quwoquan_app/scripts/device/verify_welcome_motion_frames.py
	@python3 quwoquan_app/scripts/device/verify_startup_ttid_baseline.py
	@python3 quwoquan_app/test/local_contract/runtime/startup_welcome_motion_probe__local_contract_test.py

verify-app-startup-environment-pr:
	@python3 quwoquan_ops/gate/verify_python_syntax.py \
		quwoquan_app/scripts/device/verify_flutter_run_defines.py \
		quwoquan_app/scripts/device/verify_ios_hot_restart.py
	@python3 quwoquan_app/scripts/runtime/platform/verify_startup_environment_matrix.py
	@python3 quwoquan_app/test/local_contract/runtime/ios_runtime_dart_defines__local_contract_test.py
	@python3 quwoquan_app/test/local_contract/runtime/ios_runtime_dart_defines__direct_debug__local_contract_test.py
	@python3 quwoquan_app/test/local_contract/runtime/ios_hot_restart_launcher__local_contract_test.py
	@python3 quwoquan_app/test/local_contract/runtime/startup_probe_parser__local_contract_test.py
	@python3 quwoquan_app/test/local_contract/runtime/startup_probe_parser__environment_matrix__local_contract_test.py
	@python3 quwoquan_app/test/local_contract/runtime/startup_probe_parser__matrix_evidence__local_contract_test.py
	@python3 quwoquan_app/test/local_contract/runtime/startup_probe_parser__launcher_handoff__local_contract_test.py
	@python3 quwoquan_app/test/local_contract/runtime/startup_probe_parser__android_probe__local_contract_test.py

verify-app-ios-hot-restart:
	@test -n "$(IOS_SIMULATOR_ID)" || { echo "IOS_SIMULATOR_ID is required"; exit 2; }
	@PYTHONPATH=. python3 quwoquan_app/scripts/device/verify_ios_hot_restart.py \
		--env alpha \
		--device-id "$(IOS_SIMULATOR_ID)"

verify-app-startup-environment-uat:
	@test -n "$(STARTUP_EVIDENCE_ROOT)" || { echo "GATE_BLOCK: STARTUP_EVIDENCE_ROOT is required"; exit 2; }
	@test -n "$(STARTUP_BASELINE_ID)" || { echo "GATE_BLOCK: STARTUP_BASELINE_ID is required"; exit 2; }
	@test -n "$(STARTUP_RELEASE_ID)" || { echo "GATE_BLOCK: STARTUP_RELEASE_ID is required"; exit 2; }
	@test -n "$(STARTUP_RELEASE_DIGEST)" || { echo "GATE_BLOCK: STARTUP_RELEASE_DIGEST is required"; exit 2; }
	@REPORT_PATH="$$(cd "$(STARTUP_EVIDENCE_ROOT)" && pwd)/startup-environment-matrix-report.json"; \
	python3 quwoquan_app/scripts/runtime/platform/verify_startup_environment_matrix.py \
		--evidence-root "$(STARTUP_EVIDENCE_ROOT)" \
		--require-runtime-evidence \
		--require-readback \
		--require-observability \
		--minimum-runtime-runs 20 \
		--require-physical-release \
		--baseline-id "$(STARTUP_BASELINE_ID)" \
		--release-id "$(STARTUP_RELEASE_ID)" \
		--release-digest "$(STARTUP_RELEASE_DIGEST)" \
		--report "$$REPORT_PATH" && \
	cd quwoquan_app && flutter test \
		test/user_acceptance/journeys/app_startup/startup_dual_platform_matrix__user_acceptance_test.dart \
		--dart-define=QWQ_STARTUP_MATRIX_REPORT="$$REPORT_PATH"

verify-app-startup-observability-release:
	@test -n "$(STARTUP_EVIDENCE_ROOT)" || { echo "GATE_BLOCK: STARTUP_EVIDENCE_ROOT is required"; exit 2; }
	@test -n "$(STARTUP_BASELINE_ID)" || { echo "GATE_BLOCK: STARTUP_BASELINE_ID is required"; exit 2; }
	@test -n "$(STARTUP_RELEASE_ID)" || { echo "GATE_BLOCK: STARTUP_RELEASE_ID is required"; exit 2; }
	@test -n "$(STARTUP_RELEASE_DIGEST)" || { echo "GATE_BLOCK: STARTUP_RELEASE_DIGEST is required"; exit 2; }
	@python3 quwoquan_app/scripts/runtime/platform/verify_startup_environment_matrix.py \
		--evidence-root "$(STARTUP_EVIDENCE_ROOT)" \
		--require-runtime-evidence \
		--require-readback \
		--minimum-runtime-runs 20 \
		--require-physical-release \
		--require-observability \
		--baseline-id "$(STARTUP_BASELINE_ID)" \
		--release-id "$(STARTUP_RELEASE_ID)" \
		--release-digest "$(STARTUP_RELEASE_DIGEST)"

verify-app-experience-observability:
	@python3 quwoquan_app/scripts/runtime/observability/verify_ops_event_schema_completeness.py
	@python3 -m unittest \
		quwoquan_ops.tests.local_contract.test_app_experience_observability__contract__local_contract_test

verify-app-recoverable-error-surface:
	@python3 quwoquan_app/scripts/runtime/error/verify_app_recoverable_error_surface.py

verify-app-dual-platform-usability-baseline:
	@python3 quwoquan_app/scripts/runtime/platform/verify_dual_platform_usability_baseline.py
	@$(MAKE) verify-app-startup-environment-pr
	@$(MAKE) verify-app-recoverable-error-surface
	@$(MAKE) verify-app-page-horizontal-quality

run-app-dual-platform-usability-matrix:
	@python3 quwoquan_app/scripts/device/run_dual_platform_usability_matrix.py

build-app-startup-environment-matrix:
	@test -n "$(IOS_SIMULATOR_ID)" || { echo "IOS_SIMULATOR_ID is required"; exit 2; }
	@python3 quwoquan_app/scripts/device/build_startup_environment_matrix.py \
		--ios-simulator-id "$(IOS_SIMULATOR_ID)"

verify-app-lib-test-only-symbols:
	@python3 quwoquan_app/scripts/runtime/architecture/verify_lib_no_test_only_symbols.py

# lib 不得 import test/ 树；约束由门禁源码直接表达。
verify-app-lib-no-test-import:
	@python3 quwoquan_app/scripts/runtime/architecture/verify_lib_no_import_test_tree.py

verify-app-content-ui-boundaries:
	@python3 quwoquan_app/scripts/content_service/verify_content_ui_directory_boundaries.py

verify-app-remote-config-contract:
	@python3 quwoquan_app/scripts/runtime/cloud/verify_app_remote_config_contract.py

verify-app-production-data-source-single-path:
	@python3 quwoquan_app/scripts/runtime/cloud/verify_production_data_source_single_path.py
	@python3 -m unittest \
		quwoquan_app.test.local_contract.runtime.production_release_artifact__local_contract_test

verify-production-wiring-purity: verify-app-mock-isolation verify-app-lib-test-only-symbols verify-app-production-data-source-single-path verify-app-cloud-package-boundaries verify-provider-substitute-prod-purity

verify-provider-substitute-prod-purity:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_provider_substitute_prod_purity.py

verify-test-data-architecture:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_test_data_architecture.py

verify-test-data-environment-results:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_test_data_environment_results.py $(TEST_DATA_ENVIRONMENT_RESULTS_ARGS)

verify-test-data-performance:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_test_data_performance.py $(TEST_DATA_PERFORMANCE_ARGS)

fetch-app-bundled-fonts:
	@python3 quwoquan_app/scripts/cli.py fonts fetch

verify-app-bundled-fonts:
	@python3 quwoquan_app/scripts/cli.py fonts verify

check-app-bundled-fonts-updates:
	@python3 quwoquan_app/scripts/cli.py fonts check-updates

verify-app-web-offline-resources:
	@python3 quwoquan_app/scripts/cli.py web verify-offline --build

verify-app-assistant-old-stack-retired:
	@python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_assistant_old_stack_retired.py

verify-quwoquan-data:
	@python3 quwoquan_data/scripts/cli.py verify all

.PHONY: verify-data-control-literals
verify-data-control-literals:
	@python3 quwoquan_data/scripts/cli.py verify control-literals

verify-data-release-consistency:
	@if [ -z "$(RELEASE_FILE)" ]; then \
		echo "FAIL: RELEASE_FILE is required. Example: make verify-data-release-consistency RELEASE_FILE=quwoquan_data/publish/env_releases/<releaseId>/gamma.json"; \
		exit 2; \
	fi
	@python3 quwoquan_data/scripts/cli.py verify \
		--data-release-file "$(RELEASE_FILE)" \
		$(if $(PUBLISH_ROOT),--publish-root "$(PUBLISH_ROOT)",) \
		$(if $(PHASE),--phase "$(PHASE)",)

verify-media-release-contract:
	@python3 quwoquan_data/scripts/cli.py verify media-release-contract

verify-login-dependency-config:
	@python3 quwoquan_service/scripts/user-service/verify_login_dependency_config.py

verify-markdown-article-no-article-document:
	@python3 quwoquan_app/scripts/content_service/content/post/verify_markdown_article_no_article_document.py

verify-article-contract-purity:
	@python3 quwoquan_app/scripts/content_service/content/post/verify_article_contract_purity.py

verify-app-env-package:
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env alpha >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env beta >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env gamma >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env prod >/dev/null

verify-service-env-package:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make verify-service-env-package SERVICE=content-service"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env alpha --service "$(SERVICE)" --include-services >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env beta --service "$(SERVICE)" --include-services >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env gamma --service "$(SERVICE)" --include-services >/dev/null
	@python3 quwoquan_ops/cli/stackctl.py --output-format json package --env prod --service "$(SERVICE)" --include-services >/dev/null

verify-env-topology:
	@python3 quwoquan_ops/gate/verify_environment_assembly.py

verify-prod-plane-access-isolation:
	@python3 quwoquan_ops/gate/verify_prod_plane_access_isolation.py

verify-local-port-manifest:
	@python3 quwoquan_ops/gate/verify_local_env_port_manifest.py

verify-public-vs-upstream-url-contract:
	@python3 quwoquan_app/scripts/env/verify_public_vs_upstream_url_contract.py

verify-domain-governance:
	@python3 quwoquan_ops/gate/verify_domain_governance.py

verify-python-script-governance:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_python_script_governance.py --scope all --mode check

# 垂类架构静态防回退：存量债务只减不增，已退役 travel-service 永久零缺口。
verify-vertical-architecture-ratchet:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_vertical_architecture_ratchet.py

sync-page-object-source-paths:
	@python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py --with-gate

verify-page-object-source-paths:
	@python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py --check --fail-on-review

verify-gamma-local-prod-isomorphism:
	@python3 quwoquan_ops/environments/verify/verify_gamma_local_prod_isomorphism.py

verify-app-aggregate-mock-ratchet:
	@python3 quwoquan_app/scripts/env/verify_aggregate_mock_ratchet.py

verify-api-integration-direct-storage:
	@python3 quwoquan_ops/gate/verify_api_integration_direct_storage.py

verify-error-code-assertion-coverage:
	@python3 quwoquan_ops/gate/verify_error_code_assertion_coverage.py

verify-environment-stability-final-acceptance:
	@python3 quwoquan_ops/gate/verify_environment_stability_final_acceptance.py $(ENVIRONMENT_STABILITY_ARGS)

verify-github-artifact-lifecycle:
	@python3 quwoquan_ops/gate/verify_github_artifact_lifecycle.py

# 反向错误码治理：实现发射了 stable code 但两个声明源都没有声明位。
# 存量以显式基线清单登记、只减不增；新增未声明码与新增解析盲点立刻 BLOCK。
verify-emitted-error-code-declaration:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/tests/local_contract/gate/test_emitted_error_code_declaration__contract__local_contract_test.py

verify-env-packaging:
	@deploy_work_root="$$(mktemp -d "$${TMPDIR:-/tmp}/quwoquan-deploy.XXXXXX")"; \
	trap 'rm -rf "$$deploy_work_root"' EXIT; \
	candidate="$$deploy_work_root/candidate-release.json"; \
	rollback="$$deploy_work_root/rollback-release.json"; \
	printf '%s\n' '{"schema":"quwoquan_data.release_attestation","releaseId":"packaging-contract-candidate","payloadSha256":"sha256:1111111111111111111111111111111111111111111111111111111111111111"}' >"$$candidate"; \
	printf '%s\n' '{"schema":"quwoquan_data.release_attestation","releaseId":"packaging-contract-rollback","payloadSha256":"sha256:2222222222222222222222222222222222222222222222222222222222222222"}' >"$$rollback"; \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/cli/stackctl.py --output-format json package --env alpha --include-services --release-attestation "$$candidate" --rollback-release-attestation "$$rollback" >/dev/null && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/cli/stackctl.py --output-format json package --env beta --include-services --release-attestation "$$candidate" --rollback-release-attestation "$$rollback" >/dev/null && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/cli/stackctl.py --output-format json package --env gamma --include-services --release-attestation "$$candidate" --rollback-release-attestation "$$rollback" >/dev/null && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/cli/stackctl.py --output-format json package --env prod --include-services --release-attestation "$$candidate" --rollback-release-attestation "$$rollback" >/dev/null && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/gate/verify_environment_packaging_contract.py && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_ops/gate/verify_env_artifact_isolation.py && \
	QWQ_DEPLOY_WORK_ROOT="$$deploy_work_root" python3 quwoquan_app/scripts/env/verify_prod_package_purity.py && \
	python3 quwoquan_ops/environments/verify/verify_gamma_local_prod_isomorphism.py

OBSERVABILITY_TARGET ?= alpha-local

observability-es-up:
	@python3 quwoquan_ops/cli/stackctl.py --output-format json up --target "$(OBSERVABILITY_TARGET)" --workload full --skip-app --skip-build

observability-es-down:
	@python3 quwoquan_ops/cli/stackctl.py --output-format json down --target "$(OBSERVABILITY_TARGET)"

observability-es-health:
	@python3 quwoquan_ops/cli/stackctl.py --output-format json product-telemetry-log-sink --target "$(OBSERVABILITY_TARGET)" --action health

observability-es-bootstrap:
	@python3 quwoquan_ops/cli/stackctl.py --output-format json product-telemetry-log-sink --target "$(OBSERVABILITY_TARGET)" --action cold-start

observability-es-smoke:
	@python3 quwoquan_ops/cli/stackctl.py --output-format json product-telemetry-log-sink --target "$(OBSERVABILITY_TARGET)" --action all

# 告警链路开火演练：向 Alertmanager v2 API 注入带演练标记的合成告警，不触碰真实
# 规则求值，演练告警 20 分钟自动过期。可选 PLATFORM_OPS_URL + PLATFORM_OPS_BEARER
# 校验控制面回流。证据写入 .qwq_output/env/repo/runs/alert-drill/。
observability-alert-drill:
	@ALERTMANAGER_URL="$(ALERTMANAGER_URL)" python3 quwoquan_ops/tools/alert_drill.py

verify-reliable-task-topology:
	@python3 quwoquan_service/scripts/runtime/reliabletask/verify_reliable_task_catalog.py
	@python3 quwoquan_service/scripts/runtime/reliabletask/verify_reliable_task_retention_policy.py
	@python3 quwoquan_service/scripts/runtime/packaging/verify_module_permission_scope.py
	@python3 quwoquan_service/scripts/runtime/reliabletask/verify_reliable_task_migration.py

verify-service-architecture:
	@find . \( -path './.git' -o -path './.qwq_output' \) -prune -o -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -exec rm -rf {} + ; true
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_service_architecture.py

# 唯一 canonical coverage rule（端侧行/分支 + 云侧语句，只增不减）。--collect 会真跑测试采集覆盖率，
# 因此比纯静态门禁慢；已挂入 gate_repo.sh 的 run_app / run_service 分支。
verify-canonical-coverage:
	@python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect

verify-canonical-coverage-app:
	@python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --scope app

verify-canonical-coverage-service:
	@python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --scope service

# 仅在 App/Cloud/Python/Ops 全单元同次绿采集后整体写入唯一 canonical baseline。
# 禁止 SCOPE/UNIT 分区更新，避免同一 baseline 混入不同时点的 receipt。
write-canonical-coverage-baseline:
	@python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --write-baseline

verify-metadata:
	@$(MAKE) -C quwoquan_service verify-metadata

# append_only_fact 的公开 command 不得承载实例级不变式，追加语义必须保持不可变。
verify-append-only-fact-command-admission:
	@python3 quwoquan_service/scripts/verify/structure/verify_append_only_fact_command_admission.py

# 手写 PromQL 收敛：可派生规则必须迁入 codegen，剩余规则必须在 overlay manifest 登记不可派生理由。
verify-contract-alert-overlay:
	@python3 quwoquan_ops/gate/verify_contract_alert_overlay.py

# 端云 metric 语义同源：telemetry.metric / contract_metric / operationId 三处必须同源。
verify-metric-identity-homology:
	@python3 quwoquan_ops/gate/verify_metric_identity_homology.py

# 黄金指标阈值同源：golden_metric_catalog 的 alerting.threshold 必须与告警定义逐字一致。
verify-metric-threshold-homology:
	@python3 quwoquan_ops/gate/verify_metric_threshold_homology.py

# scrape 目标同源：第一方服务的 metrics target 必须与 deploy/base containerPort 一致。
verify-prometheus-scrape-homology:
	@python3 quwoquan_ops/gate/verify_prometheus_scrape_homology.py

# Grafana 看板契约：bare model、uid 唯一且层级一致、expr 非空、规格必备看板存在。
verify-grafana-dashboard-lint:
	@python3 quwoquan_ops/gate/verify_grafana_dashboard_lint.py

# 指标存在性对账：看板/告警消费的每个 series 必须有真实 emitter/recording/
# exporter 来源；监控配置面禁止超前于代码 emit 面（幽灵指标即 BLOCK）。
verify-metric-emitter-existence:
	@python3 quwoquan_ops/gate/verify_metric_emitter_existence.py

# 页面埋点覆盖矩阵：telemetry_descriptor 交互声明必须有强类型遥测出口；
# primary 漏斗页面（登录/创作/搜索）缺埋点 BLOCK，其余入报告。
verify-page-telemetry-coverage:
	@python3 quwoquan_app/scripts/runtime/observability/report_page_telemetry_coverage.py

# 告警表达式求值回归：promtool test rules（注入序列 → 期望开火/不开火）。
verify-prometheus-rule-tests:
	@command -v promtool >/dev/null 2>&1 || { \
		echo "FAIL: promtool is required (brew install prometheus / apt install prometheus)"; exit 1; \
	}
	@promtool test rules quwoquan_ops/observability/monitoring/promtool_tests/*.yaml

# operation.privacy 派生的运行时脱敏表不得与 ContractGraph 漂移。
verify-operation-privacy-redaction:
	@$(MAKE) -C quwoquan_service verify-operation-privacy-redaction

build-app-env:
	@if [ -z "$(ENV)" ]; then \
		echo "FAIL: ENV is required. Example: make build-app-env ENV=beta"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py package --env "$(ENV)"

build-service-env:
	@if [ -z "$(SERVICE)" ] || [ -z "$(ENV)" ]; then \
		echo "FAIL: SERVICE and ENV are required. Example: make build-service-env SERVICE=content-service ENV=beta"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py package --env "$(ENV)" --service "$(SERVICE)" --include-services

stackctl-package:
	@if [ -z "$(ENV)" ]; then \
		echo "FAIL: ENV is required. Example: make stackctl-package ENV=beta INCLUDE_SERVICES=1"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py package --env "$(ENV)" $(if $(SERVICE),--service "$(SERVICE)",) $(if $(INCLUDE_SERVICES),--include-services,)

stackctl-verify:
	@if [ -z "$(PROFILE)" ]; then echo "FAIL: PROFILE is required: baseline|smoke|integration|release"; exit 2; fi
	@python3 quwoquan_ops/cli/stackctl.py verify $(if $(ENV),--env "$(ENV)",) $(if $(TARGET),--target "$(TARGET)",) $(if $(KIND),--kind "$(KIND)",) --profile "$(PROFILE)"

dev-up:
	@python3 quwoquan_ops/cli/stackctl.py up $(if $(ENV),--env "$(ENV)",) $(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",) $(if $(SKIP_APP),--skip-app,) $(if $(ROLLOUT_MODE),--rollout-mode "$(ROLLOUT_MODE)",)

dev-session:
	@if [ -z "$(ALL_NONPROD)" ] && [ -z "$(ENV)" ] && [ -z "$(TARGET)" ]; then \
		echo "FAIL: ENV or TARGET is required, or set ALL_NONPROD=1"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py dev-session \
		$(if $(ALL_NONPROD),--all-nonprod,$(if $(ENV),--env "$(ENV)",--target "$(TARGET)")) \
		$(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",) \
		$(if $(LAUNCH_APP),--launch-app,)

stackctl-up:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-up TARGET=beta-local"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py up --target "$(TARGET)" --workload "$(or $(WORKLOAD),full)" $(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",) $(if $(SKIP_APP),--skip-app,) $(if $(ROLLOUT_MODE),--rollout-mode "$(ROLLOUT_MODE)",)

stackctl-down:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-down TARGET=beta-local"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py down --target "$(TARGET)"

stackctl-status:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-status TARGET=gamma-local"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py status --target "$(TARGET)"

stackctl-health:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-health TARGET=prod-hosted"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py health --target "$(TARGET)" --scope "$(or $(SCOPE),full)"

stackctl-inspect:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-inspect TARGET=prod-hosted SCOPE=all"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py inspect --target "$(TARGET)" --scope "$(or $(SCOPE),all)"

stackctl-doctor:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-doctor TARGET=beta-local"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py doctor --target "$(TARGET)"

stackctl-repair:
	@if [ -z "$(TARGET)" ] || [ -z "$(FIX)" ]; then \
		echo "FAIL: TARGET and FIX are required. Example: make stackctl-repair TARGET=beta-local FIX=restart-stack"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py repair --target "$(TARGET)" --fix "$(FIX)"

stackctl-deploy:
	@if [ -z "$(TARGET)" ]; then \
		echo "FAIL: TARGET is required. Example: make stackctl-deploy TARGET=prod-hosted SERVICE=prod-stack FROM_CANDIDATE_DIGEST=sha256:... TO_CANDIDATE_DIGEST=sha256:... RELEASE_MANIFEST=/path/manifest.json RELEASE_EVIDENCE_REF=ghcr.io/...@sha256:... STEP=25"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py deploy --target "$(TARGET)" $(if $(STAGE),--stage "$(STAGE)",) $(if $(SERVICE),--service "$(SERVICE)",) $(if $(FROM_CANDIDATE_DIGEST),--from-candidate-digest "$(FROM_CANDIDATE_DIGEST)",) $(if $(TO_CANDIDATE_DIGEST),--to-candidate-digest "$(TO_CANDIDATE_DIGEST)",) $(if $(RELEASE_MANIFEST),--release-manifest "$(RELEASE_MANIFEST)",) $(if $(RELEASE_EVIDENCE_REF),--release-evidence-ref "$(RELEASE_EVIDENCE_REF)",) $(if $(STEP),--step "$(STEP)",)

verify-env-instance-isolation:
	@python3 quwoquan_service/scripts/runtime/packaging/verify_env_instance_isolation.py

beta-up:
	@DEVICE_ID="$(DEVICE_ID)" \
	AUTO_OPEN_OPS="$(AUTO_OPEN_OPS)" \
	SEED_VERIFY_MODE="$(SEED_VERIFY_MODE)" \
	MEDIA_MODE="$(MEDIA_MODE)" \
	LOCAL_PUBLIC_HOST="$(LOCAL_PUBLIC_HOST)" \
	GATEWAY_BASE_URL_OVERRIDE="$(GATEWAY_BASE_URL_OVERRIDE)" \
	python3 quwoquan_ops/cli/stackctl.py up --target beta-local \
		$(if $(filter 0,$(START_APP)),--skip-app,) \
		$(if $(DEVICE_ID),--device-id "$(DEVICE_ID)",) \
		$(if $(WORKLOAD),--workload "$(WORKLOAD)",)

beta-down:
	@python3 quwoquan_ops/cli/stackctl.py down --target beta-local

beta-status:
	@python3 quwoquan_ops/cli/stackctl.py status --target beta-local

# 页面质量：磁盘页面、canonical page object、route/surface 与强类型展示契约一致。
verify-app-page-horizontal-quality: verify-app-page-object-contract
	@python3 quwoquan_app/scripts/runtime/page/verify_page_abc_governance.py --quiet

verify-app-page-object-contract:
	@python3 quwoquan_service/scripts/contracts/sync_page_object_source_paths.py --check --fail-on-review
	@python3 quwoquan_app/scripts/runtime/page/verify_page_object_contract.py

verify-app-native-edge-navigation:
	@python3 quwoquan_app/scripts/runtime/page/verify_native_edge_navigation.py

verify-app-pageflip-backward-tests:
	@python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/local_contract/design_system/pageflip/pageflip_contract__local_contract_test.dart test/local_contract/design_system/pageflip/pageflip_diagnostics_visual__local_contract_test.dart test/local_contract/design_system/pageflip/pageflip_widget__local_contract_test.dart

# 后翻路线 B 主线静态门禁（见 .cursor/rules/12-pageflip-backward-mainline.mdc）。
verify-app-pageflip-backward-static:
	@python3 quwoquan_app/scripts/content_service/content/post/verify_pageflip_backward_mainline.py

# 后翻主线聚合门禁（静态扫描 + 合约/视觉测试），供规则与 commit gate 引用。
verify-app-pageflip-back-mainline: verify-app-pageflip-backward-static verify-app-pageflip-backward-tests

# 页面 A/B/C 专项扫描；默认仅报告，按需加 --enforce-*。
verify-app-page-abc-governance:
	@python3 quwoquan_app/scripts/runtime/page/verify_page_abc_governance.py

verify-app-page-abc-governance-enforce-a:
	@python3 quwoquan_app/scripts/runtime/page/verify_page_abc_governance.py --enforce-a

verify-app-page-abc-governance-enforce-b:
	@python3 quwoquan_app/scripts/runtime/page/verify_page_abc_governance.py --enforce-b

verify-app-page-abc-governance-enforce-c:
	@python3 quwoquan_app/scripts/runtime/page/verify_page_abc_governance.py --enforce-c

verify-app-page-abc-governance-enforce-all:
	@python3 quwoquan_app/scripts/runtime/page/verify_page_abc_governance.py --enforce-a --enforce-b --enforce-c

# user_profile 头像 projection：凡暴露 avatar URL，必须显式带版本字段。
verify-app-user-profile-avatar-projection-versions:
	@python3 quwoquan_app/scripts/user_service/account/user_account/verify_user_profile_avatar_projection_versions.py

# UI 层 Map<String,dynamic> 字面量零容忍（存量已清零，基线已退役，命中即 FAIL）
verify-app-ui-map-literal-budget:
	@python3 quwoquan_app/scripts/runtime/page/verify_ui_map_literal_budget.py

verify-retired-terms-zero:
	@python3 quwoquan_app/scripts/runtime/architecture/verify_retired_terms_zero.py

# 推荐标签链路 StrictTyping：禁裸 Future<dynamic>/Future<Object?> 返回契约（cloud/services/tag）
verify-app-cloud-tag-strict-typing:
	@python3 quwoquan_app/scripts/tag_service/tag/verify_cloud_tag_strict_typing.py

verify-global-increment-constraints:
	@bash quwoquan_ops/gate/scaffold/verify_global_increment_constraints.sh

verify-agent-context-contract:
	@python3 quwoquan_ops/gate/verify_agent_context_contract.py

verify-retired-runtime-architecture:
	@python3 quwoquan_ops/gate/verify_retired_runtime_architecture.py

verify-service-ddd-cqrs-baseline:
	@$(MAKE) -C quwoquan_service verify-ddd-cqrs-baseline

verify-commercial-contract-generation:
	@python3 quwoquan_ops/gate/verify_commercial_contract_generation.py

verify-behavior-event-type-contract:
	@python3 quwoquan_ops/gate/verify_behavior_event_type_contract.py

verify-object-relation-edge-type-contract:
	@python3 quwoquan_ops/gate/verify_object_relation_edge_type_contract.py

# 全域对象级告警覆盖：ContractGraph ready operation 必须有 recording rule +
# alerting rule + dashboard PromQL 消费；--write 从 ContractGraph 重建派生产物。
verify-object-alert-coverage:
	@python3 quwoquan_service/scripts/verify/observability/verify_object_alert_coverage.py
	@python3 quwoquan_ops/tests/local_contract/observability/test_object_alert_coverage__contract_graph_mapping__observability__local_contract_test.py

# 对象 × 层 × 三层测试的 readiness 证据闭合：判定源是 metadata 装载/图构建管线派生的
# ContractGraph（readinessEvidence + objectReadiness.missing），门禁只展开缺口，不重算
# readiness 规则。缺省现场派生图；--derive 为显式同义入口，--graph 只评估
# 调用者绑定的精确图字节。STRUCTURAL 维度严格要求零缺口，不读取任何基线。
verify-object-evidence-closure:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_object_evidence_closure.py
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/tests/local_contract/gate/test_object_evidence_closure__strict_zero__contract_graph__local_contract_test.py

# 动态商业闭合只接受同一候选的六项完整 trust input。Make 不推导、不签名、
# 不补默认值；缺任一项必须在构建 Go evaluator 前以 usage error 阻断。
verify-object-evidence-commercial-closure:
	@test -n "$(OBJECT_EVIDENCE_READINESS_BUNDLE)" || { echo "GATE_BLOCK missing OBJECT_EVIDENCE_READINESS_BUNDLE"; exit 2; }
	@test -n "$(OBJECT_EVIDENCE_SIGNED_CURRENT_SNAPSHOT)" || { echo "GATE_BLOCK missing OBJECT_EVIDENCE_SIGNED_CURRENT_SNAPSHOT"; exit 2; }
	@test -n "$(OBJECT_EVIDENCE_SNAPSHOT_KEYRING)" || { echo "GATE_BLOCK missing OBJECT_EVIDENCE_SNAPSHOT_KEYRING"; exit 2; }
	@test -n "$(OBJECT_EVIDENCE_RUNNER_KEYRING)" || { echo "GATE_BLOCK missing OBJECT_EVIDENCE_RUNNER_KEYRING"; exit 2; }
	@test -n "$(OBJECT_EVIDENCE_RECEIPT_ROOT)" || { echo "GATE_BLOCK missing OBJECT_EVIDENCE_RECEIPT_ROOT"; exit 2; }
	@test -n "$(OBJECT_EVIDENCE_EVIDENCE_ROOT)" || { echo "GATE_BLOCK missing OBJECT_EVIDENCE_EVIDENCE_ROOT"; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_object_evidence_closure.py \
		--require-commercial-readiness \
		--readiness-bundle "$(OBJECT_EVIDENCE_READINESS_BUNDLE)" \
		--signed-current-snapshot "$(OBJECT_EVIDENCE_SIGNED_CURRENT_SNAPSHOT)" \
		--snapshot-keyring "$(OBJECT_EVIDENCE_SNAPSHOT_KEYRING)" \
		--runner-keyring "$(OBJECT_EVIDENCE_RUNNER_KEYRING)" \
		--receipt-root "$(OBJECT_EVIDENCE_RECEIPT_ROOT)" \
		--evidence-root "$(OBJECT_EVIDENCE_EVIDENCE_ROOT)"

# 只读展开 ContractGraph authored case × execution slots。该 target 不执行
# runner、不签名，也不生产 receipt/ResultBundle；缺显式 graph 输入即 usage BLOCK。
verify-readiness-execution-plan:
	@test -n "$(READINESS_EXECUTION_PLAN_GRAPH)" || { echo "GATE_BLOCK missing READINESS_EXECUTION_PLAN_GRAPH"; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_readiness_execution_plan.py \
		--graph "$(READINESS_EXECUTION_PLAN_GRAPH)"

# 从当前 ContractGraph authored slots 与受信 runner receipt/evidence 汇聚唯一
# ReadinessResultBundle。stdout 是唯一产物；本入口不签名、不运行环境、不写 receipt。
collect-readiness-result-bundle:
	@test -n "$(READINESS_RESULT_BUNDLE_GRAPH)" || { echo "GATE_BLOCK missing READINESS_RESULT_BUNDLE_GRAPH"; exit 2; }
	@test -n "$(READINESS_RESULT_BUNDLE_RUNNER_KEYRING)" || { echo "GATE_BLOCK missing READINESS_RESULT_BUNDLE_RUNNER_KEYRING"; exit 2; }
	@test -n "$(READINESS_RESULT_BUNDLE_RECEIPT_ROOT)" || { echo "GATE_BLOCK missing READINESS_RESULT_BUNDLE_RECEIPT_ROOT"; exit 2; }
	@test -n "$(READINESS_RESULT_BUNDLE_EVIDENCE_ROOT)" || { echo "GATE_BLOCK missing READINESS_RESULT_BUNDLE_EVIDENCE_ROOT"; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/collect_readiness_result_bundle.py \
		--graph "$(READINESS_RESULT_BUNDLE_GRAPH)" \
		--runner-keyring "$(READINESS_RESULT_BUNDLE_RUNNER_KEYRING)" \
		--receipt-root "$(READINESS_RESULT_BUNDLE_RECEIPT_ROOT)" \
		--evidence-root "$(READINESS_RESULT_BUNDLE_EVIDENCE_ROOT)"

# 五域对象级 App api_integration 证据：ContractGraph 派生 generated Remote 用例与
# service api_integration 配对，并以对象/文件计数单调棘轮阻断回退。
verify-app-domain-remote-api-integration:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/tests/local_contract/gate/test_app_domain_remote_api_integration__ratchet__local_contract_test.py
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/verify_app_domain_remote_api_integration.py

verify-homepage-type-contract:
	@python3 quwoquan_ops/gate/verify_homepage_type_contract.py

verify-tag-collection-wiring:
	@python3 quwoquan_ops/gate/verify_tag_collection_wiring.py

verify-object-idempotency-dedup:
	@python3 quwoquan_ops/gate/verify_object_idempotency_dedup.py

verify-tag-closure-baseline:
	@python3 quwoquan_data/scripts/cli.py governance taxonomy closure-scorecard --gate

verify-app-cloud-runtime-single-path:
	@python3 quwoquan_app/scripts/runtime/cloud/verify_cloud_runtime_single_path.py

verify-app-cloud-security-cutovers:
	@python3 quwoquan_app/scripts/runtime/cloud/verify_cloud_security_cutovers.py

verify-app-enum-typed-binding:
	@python3 quwoquan_app/scripts/runtime/codegen/verify_app_enum_typed_binding.py

# 端侧内聚棘轮：缺层对象、DI 里的 presentation、空目录只允许减少。
verify-app-cohesion-ratchet:
	@python3 quwoquan_app/scripts/runtime/architecture/verify_app_cohesion_ratchet.py

accept-app-contract-handoff:
	@test -n "$(APP_CONTRACT_PREVIOUS_LOCK)" || { \
		echo "APP_CONTRACT_PREVIOUS_LOCK is required" >&2; exit 2; \
	}
	@test -n "$(APP_CONTRACT_PREVIOUS_LOCK_SHA256)" || { \
		echo "APP_CONTRACT_PREVIOUS_LOCK_SHA256 is required" >&2; exit 2; \
	}
	@test -n "$(APP_CONTRACT_EXPECTED_CURRENT_LOCK_SHA256)" || { \
		echo "APP_CONTRACT_EXPECTED_CURRENT_LOCK_SHA256 is required" >&2; exit 2; \
	}
	@python3 quwoquan_ops/cli/cloud_contract_handoff.py accept \
		--previous-lock "$(APP_CONTRACT_PREVIOUS_LOCK)" \
		--previous-lock-sha256 "$(APP_CONTRACT_PREVIOUS_LOCK_SHA256)" \
		--expected-current-lock-sha256 "$(APP_CONTRACT_EXPECTED_CURRENT_LOCK_SHA256)"

# 多会话并行下的收口原子链：静止探测 -> graph 重建 -> accept(快照 CAS) ->
# codegen-app 秒级衔接。breaking 非空且未审阅时硬停，不自动批准。
accept-app-contract-handoff-atomic:
	@python3 quwoquan_ops/cli/cloud_contract_handoff_atomic.py $(APP_CONTRACT_ATOMIC_ARGS)

verify-app-contract-handoff:
	@python3 quwoquan_ops/cli/cloud_contract_handoff.py verify

# ContractGraph 的实现/测试输入由编译期按 --repo-root 扫描派生，声明侧
# sourceDigestSetSha256 与 compilerHash 都覆盖不到它们。这个目标把 graph 记录的
# path+sha256 绑定与磁盘现状对一次，用来判定 graph 相对自身输入是否已过期。
verify-app-contract-handoff-inputs:
	@python3 quwoquan_ops/cli/cloud_contract_handoff.py verify-inputs

verify-app-generated-manifest:
	@python3 quwoquan_app/scripts/runtime/codegen/verify_app_generated_manifest.py
	@$(MAKE) verify-graphql-app-client

verify-graphql-app-client:
	@$(MAKE) -C quwoquan_service verify-graphql-app-client

verify-app-shell-navigation:
	@$(MAKE) -C quwoquan_service verify-app-shell-navigation

verify-app-cloud-package-boundaries:
	@python3 quwoquan_app/scripts/runtime/cloud/verify_cloud_package_boundaries.py

# 助手手写（排除 generated）+ search_repository：Map/dynamic 只减不增棘轮。
verify-app-assistant-search-weak-typing-ratchet:
	@python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_assistant_search_weak_typing_ratchet.py

verify-assistant-agent-replay-evaluation:
	@cd quwoquan_service/services/assistant-service && go test ./tests/local_contract/assistant/assistant_run -run '^TestAgentReplayEvaluationGate$$' -count=1

gate:
	@$(MAKE) verify-global-increment-constraints
	@$(MAKE) verify-agent-context-contract
	@$(MAKE) verify-retired-runtime-architecture
	@$(MAKE) verify-service-ddd-cqrs-baseline
	@$(MAKE) verify-service-architecture
	@$(MAKE) verify-commercial-contract-generation
	@$(MAKE) verify-behavior-event-type-contract
	@$(MAKE) verify-object-relation-edge-type-contract
	@$(MAKE) verify-homepage-type-contract
	@$(MAKE) verify-app-cloud-runtime-single-path
	@$(MAKE) verify-app-contract-handoff
	@$(MAKE) verify-app-contract-handoff-inputs
	@$(MAKE) verify-app-generated-manifest
	@$(MAKE) verify-app-cloud-package-boundaries
	@$(MAKE) verify-app-cloud-security-cutovers
	@$(MAKE) verify-append-only-fact-command-admission
	@$(MAKE) verify-contract-alert-overlay
	@$(MAKE) verify-metric-identity-homology
	@$(MAKE) verify-metric-threshold-homology
	@$(MAKE) verify-prometheus-scrape-homology
	@$(MAKE) verify-grafana-dashboard-lint
	@$(MAKE) verify-metric-emitter-existence
	@$(MAKE) verify-prometheus-rule-tests
	@$(MAKE) verify-page-telemetry-coverage
	@$(MAKE) verify-app-enum-typed-binding
	@$(MAKE) verify-app-cohesion-ratchet
	@$(MAKE) verify-feature-tree
	@$(MAKE) verify-assistant-agent-replay-evaluation
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-no-fake
	@$(MAKE) verify-test-nonfunctional-coverage
	# local_contract 只在 gate_repo scope 内跑一次，禁止与 test-local-contract 双跑。
	@$(MAKE) verify-reliable-task-topology
	@$(MAKE) verify-markdown-article-no-article-document
	@$(MAKE) verify-article-contract-purity
	@python3 quwoquan_ops/cli/stackctl.py verify --kind all --profile baseline
	@bash quwoquan_ops/gate/gate_repo.sh

# 环境端口与 gamma 验证 profile 分别由顶层端口清单和 gamma/validation_suites.json 定义。
gate-local-gamma:
	@if [ "$${LOCAL_GAMMA_DRY_RUN:-0}" = "1" ]; then \
		python3 quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py --dry-run; \
	else \
		set -e; \
		LG_HTTP_PORT="$${LOCAL_GAMMA_HTTP_PORT:-19000}"; \
		LG_PRODUCT_OPS_PORT="$${LOCAL_GAMMA_PRODUCT_OPS_PORT:-19010}"; \
		LG_MEDIA_PORT="$${LOCAL_GAMMA_MEDIA_EDGE_PORT:-19100}"; \
		LG_USER_PORT="$${LOCAL_GAMMA_USER_PORT:-19210}"; \
		export LOCAL_GAMMA_HTTP_PORT="$$LG_HTTP_PORT"; \
		export LOCAL_GAMMA_PRODUCT_OPS_PORT="$$LG_PRODUCT_OPS_PORT"; \
		export LOCAL_GAMMA_MEDIA_EDGE_PORT="$$LG_MEDIA_PORT"; \
		export LOCAL_GAMMA_USER_PORT="$$LG_USER_PORT"; \
		if [ "$${LOCAL_GAMMA_SKIP_GATE:-1}" != "1" ]; then $(MAKE) gate; fi; \
		$(MAKE) verify-app-env-package; \
		$(MAKE) verify-test-data-architecture; \
		python3 quwoquan_ops/cli/stackctl.py up --env gamma --skip-app --workload full; \
		python3 quwoquan_app/scripts/gamma/run_local_gamma_release_consumer_api.py; \
		bash quwoquan_app/scripts/gamma/run_local_gamma_device_uat.sh; \
		python3 quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py; \
	fi

gate-runtime-media:
	@bash quwoquan_ops/gate/gate_runtime_media.sh

gate-runtime-media-full:
	@bash quwoquan_ops/gate/gate_runtime_media.sh --full

# 群头像四环境证据机器校验（须提供 .qwq_output 中的 non-dry-run manifest）
verify-chat-avatar-commercial-matrix:
	@if [ -z "$(COMMERCIAL_MATRIX_MANIFEST)" ]; then \
		echo "FAIL: 请设置 COMMERCIAL_MATRIX_MANIFEST=$(QWQ_OUTPUT_ROOT)/env/repo/runs/commercial-matrix-chat-avatar/manifest.yaml"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/gate/verify_chat_avatar_commercial_matrix_evidence.py --manifest "$(COMMERCIAL_MATRIX_MANIFEST)"

feature-context:
	@if [ -z "$(TARGET)" ]; then echo "GATE_BLOCK: 请设置 TARGET=<spec-or-code-path>"; exit 2; fi
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py context --target "$(TARGET)"

feature-tree-overview:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py overview

feature-tree-change-report:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py change-report

feature-tree-content-review:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree_content_review.py

verify-feature-tree:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py verify --changes
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree_content_review.py

verify:
	@$(MAKE) verify-global-increment-constraints
	@$(MAKE) verify-agent-context-contract
	@$(MAKE) verify-retired-runtime-architecture
	@$(MAKE) verify-service-ddd-cqrs-baseline
	@$(MAKE) verify-service-architecture
	@$(MAKE) verify-commercial-contract-generation
	@$(MAKE) verify-app-cloud-runtime-single-path
	@$(MAKE) verify-app-contract-handoff
	@$(MAKE) verify-app-generated-manifest
	@$(MAKE) verify-app-cloud-package-boundaries
	@$(MAKE) verify-app-cloud-security-cutovers
	@$(MAKE) verify-feature-tree
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-nonfunctional-coverage
	@$(MAKE) verify-feature-tree
	@bash quwoquan_service/scripts/verify/contract_graph/verify_contract_metadata.sh
	@bash quwoquan_ops/environments/verify/verify_service_domain_layout.sh
	@bash quwoquan_service/scripts/runtime/packaging/verify_runtime_packaging.sh
	@bash quwoquan_ops/environments/verify/verify_ff_config_contract.sh
	@$(MAKE) verify-reliable-task-topology
	@bash quwoquan_service/scripts/recommendation-service/verify_recommendation_service_contract.sh
	@$(MAKE) verify-quwoquan-data

codegen:
	@$(MAKE) -C quwoquan_service codegen

codegen-observability-catalog:
	@$(MAKE) -C quwoquan_service codegen-observability-catalog

verify-observability-catalog:
	@$(MAKE) -C quwoquan_service verify-observability-catalog

verify-runtime-log-governance:
	@python3 quwoquan_ops/gate/verify_runtime_log_governance.py

codegen-app:
	@$(MAKE) verify-app-contract-handoff
	@$(MAKE) -C quwoquan_service codegen-app
	@$(MAKE) -C quwoquan_service codegen-graphql-app-client
	@$(MAKE) codegen-app-shell-navigation
	@$(MAKE) verify-app-generated-manifest

codegen-app-shell-navigation:
	@$(MAKE) -C quwoquan_service codegen-app-shell-navigation

codegen-ops-portal:
	@$(MAKE) -C quwoquan_service codegen-ops-portal

codegen-control-plane-runtime:
	@$(MAKE) -C quwoquan_service codegen-control-plane-runtime

codegen-chat-service:
	@$(MAKE) -C quwoquan_service codegen-chat-service

codegen-content-service:
	@$(MAKE) -C quwoquan_service codegen-content-service

# Create one metadata-owned, object-first service vertical slice.
# Usage:
#   make new-service SERVICE=user-service CONTEXT=user.account OBJECT=user_account LANGUAGE=go
new-service:
	@if [ -z "$(SERVICE)" ] || [ -z "$(CONTEXT)" ] || [ -z "$(OBJECT)" ] || [ -z "$(LANGUAGE)" ]; then \
		echo "FAIL: SERVICE, CONTEXT, OBJECT and LANGUAGE are required"; \
		echo "Example: make new-service SERVICE=user-service CONTEXT=user.account OBJECT=user_account LANGUAGE=go"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/gate/scaffold/new_service.py \
		--service "$(SERVICE)" \
		--context "$(CONTEXT)" \
		--object "$(OBJECT)" \
		--language "$(LANGUAGE)"

# Evaluate SLO gate decision for a rollout stage.
# SLO 数值只从 Prometheus 读回（OPEN-004 关闭调用方数字旁路）。
# Example:
# make config-slo-gate PROMETHEUS_URL=http://prometheus:9090
config-slo-gate:
	@if [ -z "$(PROMETHEUS_URL)" ]; then \
		echo "FAIL: PROMETHEUS_URL is required; SLO values are read back from monitoring only"; \
		exit 2; \
	fi
	@python3 quwoquan_ops/cli/stackctl.py verify --kind config-slo --profile baseline --prometheus-url "$(PROMETHEUS_URL)"

.PHONY: commit-gate gate-smoke gate-integration gate-release test-api-contract test-api-contract-chat

# L0 本地入库门禁（pre-commit 同源）：并行静态 + 影响面测试，目标 ≤10m / 硬顶 15m。
commit-gate:
	@bash quwoquan_ops/gate/commit_gate.sh
.PHONY: prepare-test-python verify-test-no-fake verify-test-nonfunctional-coverage verify-test-directory-layout verify-test-coverage-map
.PHONY: verify-execution-profiles
.PHONY: test-local-contract test-app-python-local-contract test-runtime-local-contract test-api-integration test-runtime-api-integration test-runtime-api-integration-gamma test-user-acceptance verify-homepage-performance-evidence

prepare-test-python:
	@python3 quwoquan_ops/cli/prepare_test_python.py

# 垂类架构唯一 local_contract 入口：target-only 控制面、永久零缺口与跨主题复用合同。
test-vertical-architecture-ratchet-local-contract: prepare-test-python
	@$(DATA_PYTHON) $(PYTEST_INTERPRETER_FLAGS) -c 'import pytest' || { \
		echo "[test-vertical-architecture-ratchet-local-contract] FAIL: DATA_PYTHON missing pytest: $(DATA_PYTHON)"; \
		exit 1; \
	}
	@$(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) \
		quwoquan_ops/tests/local_contract/stackctl/test_travel_to_gathering_migration__cutover_rollback__local_contract_test.py \
		quwoquan_ops/tests/local_contract/stackctl/test_travel_to_gathering_migration__mapping__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_vertical_architecture_ratchet__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_campus_gathering_reuse__metadata__local_contract_test.py \
		-q

# App Python local_contract 与 Flutter/Dart 使用同一 canonical layer 根；pytest
# 只发现 *_test.py，因此不会重复执行同目录下的 Dart 测试。
test-app-python-local-contract: prepare-test-python
	@$(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) \
		quwoquan_app/test/local_contract -q

# 门禁配套 local_contract：这些测试锁定 gate 链上门禁自身的判据，必须与门禁同进同退。
# 缺口清单由 verify_gate_local_contract_execution.py 实时派生，本目标必须与之保持零缺口；
# 新增门禁时把它的配套测试补进这里，不要重新引入 allowance 基线。
test-gate-companion-local-contract: prepare-test-python
	@$(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) \
		quwoquan_ops/tests/local_contract/provider/test_external_provider_governance__local_contract_test.py \
		quwoquan_ops/tests/local_contract/provider/test_provider_conformance_evidence__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/provider/test_provider_conformance_evidence_active_candidate__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/provider/test_provider_conformance_evidence_two_device_remote__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/provider/test_provider_conformance_evidence_source_coverage__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/provider/test_provider_conformance_evidence_attestation_promotion__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_api_path_unversioned__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_app_architecture__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_app_client_contract_kind_alignment__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_behavior_event_type_contract__shared_enum_parity__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_canonical_recommendation_policy__local_contract_test.py \
		quwoquan_ops/tests/local_contract/ci/test_ci_cd_evidence_contracts__canonical__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_canonical_coverage__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_canonical_coverage_collection_targets__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_canonical_coverage_parsers__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_canonical_coverage_unit_measurement__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_canonical_coverage_rule_semantics__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_canonical_coverage_baseline_provenance__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_canonical_coverage_no_escape__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_canonical_coverage_app_sharding__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_api_integration_direct_storage__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_error_code_assertion_coverage__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_ratchet_baseline_governance__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_ratchet_baseline_io__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_nil_semantics__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_null_failure_isolation__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_service_contract_view_pruning__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_object_evidence_work_root_pruning__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_app_network_image_baseline_monotonicity__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_directory_layout__app_domain_dirs_from_roster__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_directory_layout__cross_cutting_and_ops_naming__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_directory_layout__app_domain_dirs_verify_app_behavior__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_directory_layout__canonical_service_tests__local_contract_test.py \
		quwoquan_ops/tests/local_contract/environment/test_env_artifact_isolation__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_git_branch_policy__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_github_supply_chain__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_homepage_type_contract__shared_enum_parity__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/environment/test_local_dependency_purity__local_contract_test.py \
		quwoquan_ops/tests/local_contract/test_data/test_test_data_architecture_gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/test_data/test_test_data_environment_results__local_contract_test.py \
		quwoquan_ops/tests/local_contract/test_data/test_test_data_performance__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_object_assistant_access_closure__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_object_idempotency_dedup__declared_required_without_dedup__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_object_relation_edge_type_contract__shared_enum_parity__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_object_search_policy_closure__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_readiness_case_coverage__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_readiness_result_bundle_collector__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_runtime_host_literals__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_search_index_field_drift__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_stage_name_identifiers__gate__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_retired_runtime_architecture__local_contract_test.py \
		quwoquan_ops/tests/local_contract/observability/test_runtime_log_governance__candidate_owned_elasticsearch__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_service_architecture__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_tag_collection_wiring__unwired_channel_baseline__contract__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_test_coverage_map__local_contract_test.py \
		quwoquan_ops/tests/local_contract/gate/test_verifier_root_discovery__gate__local_contract_test.py \
		-q

verify-test-no-fake:
	@python3 quwoquan_ops/gate/scaffold/verify_test_no_fake.py

verify-test-nonfunctional-coverage:
	@python3 quwoquan_ops/gate/scaffold/verify_runtime_error_coverage.py
	@python3 quwoquan_ops/gate/scaffold/verify_security_coverage.py
	@python3 quwoquan_ops/gate/scaffold/verify_performance_budget.py
	@python3 quwoquan_ops/gate/scaffold/verify_observability_coverage.py
	@python3 quwoquan_ops/gate/scaffold/verify_data_consistency_coverage.py
	@python3 quwoquan_ops/gate/scaffold/verify_quality_axis_coverage.py

# 四质量轴复合标签覆盖棘轮（可独立执行；亦随 verify-test-nonfunctional-coverage 运行）。
verify-quality-axis-coverage:
	@python3 quwoquan_ops/gate/scaffold/verify_quality_axis_coverage.py

# 棘轮基线治理留痕：owner/reason/expires_when/measure 必须齐备，且换度量口径时
# 必须同批写下旧口径与旧口径实测值。换口径重建基线是这类债务唯一的无痕逃逸方式。
verify-ratchet-baseline-governance:
	@python3 quwoquan_ops/gate/verify_ratchet_baseline_governance.py

# 派生「对象 x 质量轴 x 测试层」覆盖热力图（幂等报告，写入 .qwq_output/env/repo/runs/）。
test-coverage-heatmap:
	@python3 quwoquan_ops/gate/scaffold/verify_quality_axis_coverage.py --report

# 聚合执行各域性能预算测试（会话首帧/滚动/发送预算 + 图片缓存上界 + content feed p95 预算）。
verify-performance-budgets:
	@python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py \
		test/local_contract/service/chat_service/chat/message/message_timeline_scroll_send_budget__performance__local_contract_test.dart \
		test/local_contract/runtime/platform/media/image_cache_budget__performance__local_contract_test.dart
	@cd quwoquan_service && go test ./services/content-service/tests/local_contract/content/post/application/feed/ \
		-run FeedQueryLatencyBudget -count=1

# 告警演练闭环合约门禁（drill 编排闭环 + 回执契约）。
verify-alert-drill-closure:
	@$(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) \
		quwoquan_ops/tests/local_contract/stackctl/test_fault_drill_orchestration__reliability__local_contract_test.py \
		quwoquan_ops/tests/local_contract/stackctl/test_loadtest_orchestration__performance__local_contract_test.py \
		-q

verify-homepage-performance-evidence:
	@python3 quwoquan_ops/gate/scaffold/verify_performance_budget.py --require-candidate $(if $(PERFORMANCE_EVIDENCE),--evidence "$(PERFORMANCE_EVIDENCE)",) $(if $(PERFORMANCE_ARTIFACT_ROOT),--artifact-root "$(PERFORMANCE_ARTIFACT_ROOT)",)

verify-test-directory-layout:
	@python3 quwoquan_ops/gate/scaffold/verify_test_directory_layout.py

verify-test-coverage-map:
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/cli/feature_tree.py verify
	@PYTHONDONTWRITEBYTECODE=1 python3 quwoquan_ops/gate/scaffold/verify_test_coverage_map.py

verify-execution-profiles:
	@python3 quwoquan_ops/gate/verify_execution_profiles.py

verify-test-remote-env:
	@python3 quwoquan_ops/gate/scaffold/verify_test_remote_env.py --suite "$${MODE:?set MODE=api_integration|user_acceptance}" --env "$${ENV:-gamma}" --target "$${TARGET:-gamma-local}"

test-runtime-local-contract:
	@cd quwoquan_service && go test ./runtime/... -count=1 -p=$(GO_TEST_PACKAGE_PARALLELISM)

test-runtime-api-integration:
	@$(MAKE) -C quwoquan_service test-runtime-api-integration

test-runtime-api-integration-gamma:
	@bash quwoquan_ops/cli/gamma/run_reliabletask_gamma_api_integration.sh

test-local-contract:
	@$(MAKE) prepare-test-python
	@$(DATA_PYTHON) -c 'import pytest' || { echo "[test-local-contract] FAIL: DATA_PYTHON missing pytest: $(DATA_PYTHON)"; exit 1; }
	@$(MAKE) verify-feature-tree
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-no-fake
	@$(MAKE) verify-test-nonfunctional-coverage
	@$(MAKE) verify-execution-profiles
	@bash quwoquan_service/scripts/verify/contract_graph/verify_contract_metadata.sh
	@$(MAKE) test-runtime-local-contract
	@python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/local_contract/
	@$(MAKE) test-app-python-local-contract
	@cd quwoquan_service && go test $$(go list ./services/... | grep -v '/tests/api_integration') -count=1 -p=$(GO_TEST_PACKAGE_PARALLELISM)
	@mkdir -p "$(QWQ_OUTPUT_ROOT)/env/repo/runs/tests"
	@rm -rf "$(QWQ_OUTPUT_ROOT)/env/repo/runs/tests"/data-local-contract.*
	@DATA_TEST_OUTPUT_ROOT="$$(mktemp -d "$(QWQ_OUTPUT_ROOT)/env/repo/runs/tests/data-local-contract.XXXXXX")"; \
		trap 'rm -rf "$$DATA_TEST_OUTPUT_ROOT"' EXIT; \
		QWQ_OUTPUT_ROOT="$$DATA_TEST_OUTPUT_ROOT" $(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) \
			quwoquan_data/tests/local_contract quwoquan_ops/tests/local_contract -q; \
		status=$$?; \
		rm -rf "$$DATA_TEST_OUTPUT_ROOT"; \
		trap - EXIT; \
		exit $$status
	@rm -rf "$(QWQ_OUTPUT_ROOT)/env/repo/runs/tests"/data-local-contract.*
	@python3 -B quwoquan_data/scripts/cli.py verify all

# api_integration：按统一环境名解析 HTTP 基址。API_CONTRACT_ENV 默认为 gamma。
# 变量格式：{ALPHA|BETA|GAMMA|PROD}_BASE_URL 与 *_PRODUCT_OPS_BASE_URL。
test-api-contract:
	@ENV_NAME="$${API_CONTRACT_ENV:-gamma}"; \
	case "$$ENV_NAME" in \
		alpha) BASE_URL="$${ALPHA_BASE_URL:-}"; OPS_BASE_URL="$${ALPHA_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${ALPHA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		beta) BASE_URL="$${BETA_BASE_URL:-}"; OPS_BASE_URL="$${BETA_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${BETA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		gamma) BASE_URL="$${GAMMA_BASE_URL:-}"; OPS_BASE_URL="$${GAMMA_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		prod) BASE_URL="$${PROD_BASE_URL:-}"; OPS_BASE_URL="$${PROD_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${PROD_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		*) echo "[L3] FAIL: API_CONTRACT_ENV must be one of alpha|beta|gamma|prod, got $$ENV_NAME"; exit 2 ;; \
	esac; \
	if [ -z "$$BASE_URL" ] || [ -z "$$OPS_BASE_URL" ]; then \
		echo "[L3] FAIL: set $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_BASE_URL and $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_PRODUCT_OPS_BASE_URL"; \
		exit 2; \
	fi; \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py \
		test/api_integration/service/content_service/content/post/content_post_remote__api_integration_test.dart \
		test/api_integration/service/content_service/content/content_behavior_fact/content_behavior_fact_remote__api_integration_test.dart \
		test/api_integration/service/content_service/trust_safety/report/content_report_remote__api_integration_test.dart \
		test/api_integration/service/user_service/relationship/persona_relationship/persona_block_remote__api_integration_test.dart \
		test/api_integration/service/user_service/account/user_settings/privacy_settings_remote__api_integration_test.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL \
		--dart-define=LOCAL_GAMMA_T3_SCOPE=$${LOCAL_GAMMA_T3_SCOPE:-} \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN && \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py \
		test/api_integration/service/user_service/account/account_session/account_session_remote__api_integration_test.dart \
		test/api_integration/service/user_service/account/user_settings/user_settings_remote__api_integration_test.dart \
		test/api_integration/service/user_service/account/user_account/account_closure_remote__api_integration_test.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL && \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py \
		test/api_integration/service/product_ops_service/product_ops/app_release/app_release_recovery_remote__api_integration_test.dart \
		test/api_integration/service/product_ops_service/product_ops/event_record/event_record_remote__api_integration_test.dart \
		test/api_integration/service/product_ops_service/product_ops/visit_record/visit_record_remote__api_integration_test.dart \
		test/api_integration/service/product_ops_service/product_ops/recovery_failure/recovery_failure_remote__api_integration_test.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL=$$OPS_BASE_URL \
		--dart-define=API_CONTRACT_AUTH_BASE_URL=$$BASE_URL

test-api-contract-chat:
	@ENV_NAME="$${API_CONTRACT_ENV:-gamma}"; \
	case "$$ENV_NAME" in \
		alpha) BASE_URL="$${ALPHA_BASE_URL:-}"; AUTH_TOKEN="$${ALPHA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		beta) BASE_URL="$${BETA_BASE_URL:-}"; AUTH_TOKEN="$${BETA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		gamma) BASE_URL="$${GAMMA_BASE_URL:-}"; AUTH_TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		prod) BASE_URL="$${PROD_BASE_URL:-}"; AUTH_TOKEN="$${PROD_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		*) echo "[L3] FAIL: API_CONTRACT_ENV must be one of alpha|beta|gamma|prod, got $$ENV_NAME"; exit 2 ;; \
	esac; \
	if [ -z "$$BASE_URL" ]; then \
		echo "[L3] FAIL: set $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_BASE_URL"; \
		exit 2; \
	fi; \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py \
		test/api_integration/service/chat_service/chat/conversation/conversation_remote__api_integration_test.dart \
		test/api_integration/service/chat_service/chat/message/message_remote__api_integration_test.dart \
		test/api_integration/service/chat_service/chat/conversation_membership/conversation_membership_remote__api_integration_test.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN

test-app-api-integration:
	@ENV_NAME="$${ENV:-gamma}"; \
	case "$$ENV_NAME" in \
		beta) BASE_URL="$${BETA_BASE_URL:-}"; AUTH_TOKEN="$${BETA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		gamma) BASE_URL="$${GAMMA_BASE_URL:-}"; AUTH_TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		*) echo "[api_integration] FAIL: ENV must be beta or gamma; Prod requires a separately approved readiness-only flow, got $$ENV_NAME"; exit 2 ;; \
	esac; \
	if [ -z "$$BASE_URL" ]; then \
		echo "[api_integration] FAIL: set $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_BASE_URL"; \
		exit 2; \
	fi; \
	python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/api_integration \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL \
		--dart-define=APP_RUNTIME_ENV=$$ENV_NAME \
		--dart-define=APP_DATA_SOURCE=remote \
		--dart-define=CLOUD_GATEWAY_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN

test-api-integration:
	@$(MAKE) prepare-test-python
	@$(MAKE) verify-test-directory-layout
	@$(MAKE) verify-test-remote-env MODE=api_integration ENV="$${ENV:-gamma}"
	@$(MAKE) test-runtime-api-integration
	@$(MAKE) test-app-api-integration ENV="$${ENV:-gamma}"
	@cd quwoquan_service && go test $$(go list ./services/... | rg '/tests/api_integration') -count=1 -p=$(API_INTEGRATION_GO_TEST_PACKAGE_PARALLELISM)
	@$(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) quwoquan_data/tests/api_integration quwoquan_ops/tests/acceptance/api_integration -q
	@$(MAKE) test-api-contract API_CONTRACT_ENV="$${ENV:-gamma}"
	@$(MAKE) test-api-contract-chat API_CONTRACT_ENV="$${ENV:-gamma}"

test-user-acceptance:
	@$(MAKE) prepare-test-python
	@$(MAKE) verify-test-remote-env MODE=user_acceptance TARGET="$${TARGET:-gamma-local}"
	@TARGET_NAME="$${TARGET:-gamma-local}"; \
	case "$$TARGET_NAME" in \
		local) python3 quwoquan_app/scripts/env/run_flutter_test_guarded.py test/user_acceptance/ && $(PYTEST_RUNNER) $(PYTEST_INTERPRETER_FLAGS) -m pytest $(PYTEST_FLAGS) quwoquan_data/tests/user_acceptance quwoquan_ops/tests/acceptance/user_acceptance -q ;; \
		gamma-local) $(MAKE) gate-local-gamma LOCAL_GAMMA_SKIP_GATE=1 ;; \
		prod-hosted) \
			if [ -z "$${PROD_BASE_URL:-}" ] || [ -z "$${PROD_PRODUCT_OPS_BASE_URL:-}" ]; then \
				echo "[user_acceptance] FAIL: PROD_BASE_URL and PROD_PRODUCT_OPS_BASE_URL are required for prod-hosted"; \
				exit 2; \
			fi; \
			TEST_TOKEN="$${PROD_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}"; \
			if [ -z "$$TEST_TOKEN" ]; then \
				echo "[user_acceptance] FAIL: PROD_TEST_AUTH_TOKEN or TEST_AUTH_TOKEN is required for prod-hosted"; \
				exit 2; \
			fi; \
			DRY_RUN_FLAG=""; \
			if [ "$${USER_ACCEPTANCE_DRY_RUN:-0}" = "1" ]; then \
				DRY_RUN_FLAG="--dry-run"; \
			elif ! command -v patrol >/dev/null 2>&1; then \
				echo "[user_acceptance] GATE_BLOCK: patrol CLI not found; install patrol or set USER_ACCEPTANCE_DRY_RUN=1 for wiring-only verification"; \
				exit 2; \
			fi; \
			python3 quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py \
				--report "$${PROD_USER_ACCEPTANCE_REPORT:-$(QWQ_OUTPUT_ROOT)/env/prod/runs/device-matrix/environment-smoke-prod-rollout-gray-initial.json}" \
				--env-name prod \
				--rollout-stage gray-initial \
				--runtime-env prod \
				--api-contract-env prod \
				--data-source remote \
				--gateway-base-url "$${PROD_BASE_URL}" \
				--product-ops-base-url "$${PROD_PRODUCT_OPS_BASE_URL}" \
				--media-avatar-base-url "$${PROD_MEDIA_AVATAR_BASE_URL}" \
				--media-image-base-url "$${PROD_MEDIA_IMAGE_BASE_URL}" \
				--media-video-base-url "$${PROD_MEDIA_VIDEO_BASE_URL}" \
				--media-upload-base-url "$${PROD_MEDIA_UPLOAD_BASE_URL}" \
				--rtc-media-connection-url "$${PROD_RTC_MEDIA_CONNECTION_URL}" \
				--test-auth-token "$$TEST_TOKEN" \
				$$DRY_RUN_FLAG ;; \
		*) echo "[user_acceptance] FAIL: TARGET must be local, gamma-local or prod-hosted, got $$TARGET_NAME"; exit 2 ;; \
	esac

gate-smoke:
	@$(MAKE) gate
	@python3 quwoquan_ops/cli/stackctl.py verify --env alpha --kind all --profile smoke

gate-integration:
	@if [ "$(ENV)" != "beta" ] && [ "$(ENV)" != "gamma" ]; then echo "FAIL: ENV must be beta or gamma"; exit 2; fi
	@$(MAKE) gate
	@python3 quwoquan_ops/cli/stackctl.py verify --env "$(ENV)" --kind all --profile integration

gate-release:
	@if [ "$(ENV)" != "gamma" ] && [ "$(ENV)" != "prod" ]; then echo "FAIL: ENV must be gamma or prod"; exit 2; fi
	@$(MAKE) gate
	@$(MAKE) test-runtime-api-integration
	@python3 quwoquan_ops/gate/verify_provider_conformance_evidence.py --require-ready "$(ENV)"
	@python3 quwoquan_ops/cli/stackctl.py verify --env "$(ENV)" --kind all --profile release

# Deploy to beta integration K8s. CLOUD_PROVIDER=aliyun|volcengine|huaweicloud (default: aliyun).
# Usage: make deploy-beta-k8s [CLOUD_PROVIDER=volcengine]
.PHONY: deploy-beta-k8s
deploy-beta-k8s:
	@python3 quwoquan_ops/cli/stackctl.py deploy --env beta --mode environment-assembly
