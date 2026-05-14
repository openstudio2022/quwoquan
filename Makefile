.PHONY: gate
.PHONY: gate-local-gamma
.PHONY: gate-runtime-media
.PHONY: gate-runtime-media-full
.PHONY: verify-chat-avatar-commercial-matrix
.PHONY: run-chat-avatar-commercial-matrix-local
.PHONY: verify-app-mock-isolation
.PHONY: verify-app-lib-no-test-import
.PHONY: verify-app-page-horizontal-quality
.PHONY: verify-app-pageflip-back-mainline
.PHONY: verify-app-pageflip-backward-mainline
.PHONY: verify-app-page-abc-governance
.PHONY: verify-app-page-abc-governance-enforce-a
.PHONY: verify-app-page-abc-governance-enforce-b
.PHONY: verify-app-page-abc-governance-enforce-c
.PHONY: verify-app-page-abc-governance-enforce-all
.PHONY: verify-app-ui-map-literal-budget
.PHONY: verify-app-session-b-current
.PHONY: verify-app-assistant-search-weak-typing-ratchet
.PHONY: verify-app-assistant-old-stack-retired
.PHONY: verify-retired-terms-zero
.PHONY: verify-app-ui-app-data-source-mode-ratchet
.PHONY: verify-app-seed-manifest
.PHONY: verify-avatar-user-pool
.PHONY: probe-avatar-user-pool-gateway
.PHONY: verify-business-env-data-inventory
.PHONY: verify-quwoquan-data
.PHONY: verify-markdown-article-no-article-document
.PHONY: verify-quwoquan-data-post-packages
.PHONY: verify-app-env-package
.PHONY: verify-service-env-package
.PHONY: verify-env-instance-isolation
.PHONY: observability-es-up
.PHONY: observability-es-down
.PHONY: observability-es-health
.PHONY: observability-es-bootstrap
.PHONY: observability-es-smoke
.PHONY: verify-reliable-task-topology
.PHONY: build-app-env
.PHONY: build-service-env
.PHONY: test-app-alpha-seed
.PHONY: test-app-beta-seed
.PHONY: verify
.PHONY: codegen
.PHONY: codegen-app
.PHONY: codegen-ops-portal
.PHONY: codegen-control-plane-runtime
.PHONY: codegen-content-service
.PHONY: bootstrap-service-config
.PHONY: new-service
.PHONY: config-gray-rollout
.PHONY: config-rollback
.PHONY: config-slo-gate

# 客户端：UI/App/Core 不得直连 cloud/services/*/mock（过渡期见 specs/gates/ui_mock_isolation_allowlist.yaml）
verify-app-mock-isolation:
	@python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py

verify-app-lib-test-only-symbols:
	@python3 quwoquan_app/scripts/runtime/verify_lib_no_test_only_symbols.py

# lib 不得 import test/ 树（见 specs/gates/mock_test_separation_roadmap.md）
verify-app-lib-no-test-import:
	@python3 quwoquan_app/scripts/runtime/verify_lib_no_import_test_tree.py

# UI 层 AppDataSourceMode.mock / appDataSourceModeProvider 引用棘轮（见 specs/gates/ui_app_data_source_mode_baseline.json）
verify-app-ui-app-data-source-mode-ratchet:
	@python3 quwoquan_app/scripts/env/verify_ui_app_data_source_mode_ratchet.py

verify-app-seed-manifest:
	@python3 quwoquan_app/scripts/env/verify_app_seed_manifests.py

verify-app-assistant-old-stack-retired:
	@python3 agent_ops/assistant/verify_assistant_old_stack_retired.py

verify-avatar-user-pool:
	@python3 agent_ops/avatar/verify_avatar_user_pool_consistency.py

probe-avatar-user-pool-gateway:
	@python3 agent_ops/avatar/probe_avatar_user_pool_gateway.py

verify-business-env-data-inventory:
	@python3 quwoquan_app/scripts/env/verify_business_env_data_inventory.py

verify-quwoquan-data:
	@bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh

verify-markdown-article-no-article-document:
	@python3 quwoquan_app/scripts/content/verify_markdown_article_no_article_document.py

verify-quwoquan-data-post-packages:
	@python3 quwoquan_data/scripts/verify/verify_quwoquan_data_post_packages.py

verify-app-env-package:
	@bash quwoquan_app/scripts/env/build_app_env_package.sh --env alpha
	@bash quwoquan_app/scripts/env/build_app_env_package.sh --env beta
	@bash quwoquan_app/scripts/env/build_app_env_package.sh --env gamma
	@bash quwoquan_app/scripts/env/build_app_env_package.sh --env prod-gray
	@bash quwoquan_app/scripts/env/build_app_env_package.sh --env prod

verify-service-env-package:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make verify-service-env-package SERVICE=content-service"; \
		exit 2; \
	fi
	@bash quwoquan_service/scripts/runtime/build_service_env_package.sh --service "$(SERVICE)" --env alpha
	@bash quwoquan_service/scripts/runtime/build_service_env_package.sh --service "$(SERVICE)" --env beta
	@bash quwoquan_service/scripts/runtime/build_service_env_package.sh --service "$(SERVICE)" --env gamma
	@bash quwoquan_service/scripts/runtime/build_service_env_package.sh --service "$(SERVICE)" --env prod-gray
	@bash quwoquan_service/scripts/runtime/build_service_env_package.sh --service "$(SERVICE)" --env prod

observability-es-up:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py up

observability-es-down:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py down

observability-es-health:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py health

observability-es-bootstrap:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py bootstrap

observability-es-smoke:
	@python3 quwoquan_service/scripts/runtime/observability/es_cli.py smoke

verify-reliable-task-topology:
	@python3 quwoquan_app/scripts/runtime/verify_module_package_mapping.py
	@python3 quwoquan_service/scripts/recommendation/verify_reliable_task_catalog.py
	@python3 quwoquan_service/scripts/recommendation/verify_reliable_task_retention_policy.py
	@python3 quwoquan_service/scripts/runtime/verify_module_permission_scope.py
	@python3 quwoquan_service/scripts/recommendation/verify_reliable_task_migration.py

build-app-env:
	@if [ -z "$(ENV)" ]; then \
		echo "FAIL: ENV is required. Example: make build-app-env ENV=beta"; \
		exit 2; \
	fi
	@bash quwoquan_app/scripts/env/build_app_env_package.sh --env "$(ENV)"

build-service-env:
	@if [ -z "$(SERVICE)" ] || [ -z "$(ENV)" ]; then \
		echo "FAIL: SERVICE and ENV are required. Example: make build-service-env SERVICE=content-service ENV=beta"; \
		exit 2; \
	fi
	@bash quwoquan_service/scripts/runtime/build_service_env_package.sh --service "$(SERVICE)" --env "$(ENV)"

verify-env-instance-isolation:
	@python3 quwoquan_service/scripts/runtime/verify_env_instance_isolation.py

test-app-alpha-seed:
	@cd quwoquan_app && flutter test test/cloud/services/contract_seeded_mock_repository_test.dart

test-app-beta-seed:
	@python3 quwoquan_app/scripts/env/run_app_alpha_beta_seed_matrix.py

# 页面横向质量：矩阵列合法 + 磁盘路径与矩阵一致 + P2 清单 ⊆（与 gate app 段同向子集）
verify-app-page-horizontal-quality:
	@python3 quwoquan_app/scripts/runtime/verify_page_horizontal_quality_matrix.py
	@python3 quwoquan_app/scripts/runtime/verify_page_matrix_scan_complete.py

verify-app-pageflip-back-mainline:
	@cd quwoquan_app && flutter test test/components/pageflip/pageflip_contract_test.dart test/common/pageflip/pageflip_diagnostics_visual_test.dart

# 后翻路线 B 主线静态门禁（见 .cursor/rules/12-pageflip-backward-mainline.mdc）。
verify-app-pageflip-backward-mainline:
	@python3 quwoquan_app/scripts/content/verify_pageflip_backward_mainline.py

# 页面 A/B/C 专项扫描（默认仅报告、exit 0；加 --enforce-* 见 specs/gates/page_abc_governance.md）
verify-app-page-abc-governance:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py

verify-app-page-abc-governance-enforce-a:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-a

verify-app-page-abc-governance-enforce-b:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-b

verify-app-page-abc-governance-enforce-c:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-c

verify-app-page-abc-governance-enforce-all:
	@python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-a --enforce-b --enforce-c

# UI 层 Map<String,dynamic> 字面量防回退（见 specs/gates/ui_map_literal_budget.json）
verify-app-ui-map-literal-budget:
	@python3 quwoquan_app/scripts/runtime/verify_ui_map_literal_budget.py

verify-app-session-b-current:
	@python3 quwoquan_app/scripts/runtime/verify_session_b_current_governance.py

verify-retired-terms-zero:
	@python3 quwoquan_app/scripts/runtime/verify_retired_terms_zero.py

# 助手手写（排除 generated）+ search_repository：Map/dynamic 计数棘轮（见 specs/gates/assistant_search_weak_typing_governance.md）
verify-app-assistant-search-weak-typing-ratchet:
	@python3 agent_ops/avatar/verify_assistant_search_weak_typing_ratchet.py

gate:
	@bash quwoquan_service/scripts/deploy/verify_deployment_domain_mapping.sh
	@bash quwoquan_service/scripts/deploy/verify_topology_contract_regression.sh
	@$(MAKE) verify-reliable-task-topology
	@$(MAKE) verify-avatar-user-pool
	@$(MAKE) probe-avatar-user-pool-gateway
	@$(MAKE) verify-markdown-article-no-article-document
	@bash quwoquan_service/scripts/deploy/report_deployment_mapping_impact.sh
	@bash agent_ops/gate/gate_repo.sh

# 前置说明：Docker Hub 限流、Colima 磁盘、构建上下文见 deploy/shared/environment_matrix.md §2.1.1
gate-local-gamma:
	@if [ "$${LOCAL_GAMMA_DRY_RUN:-0}" = "1" ]; then \
		python3 quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py --dry-run; \
	else \
		set -e; \
		LG_HTTP_PORT="$${LOCAL_GAMMA_HTTP_PORT:-18180}"; \
		LG_PRODUCT_OPS_PORT="$${LOCAL_GAMMA_PRODUCT_OPS_PORT:-18186}"; \
		export LOCAL_GAMMA_HTTP_PORT="$$LG_HTTP_PORT"; \
		export LOCAL_GAMMA_PRODUCT_OPS_PORT="$$LG_PRODUCT_OPS_PORT"; \
		export LOCAL_GAMMA_GATEWAY_BASE_URL="$${LOCAL_GAMMA_GATEWAY_BASE_URL:-http://127.0.0.1:$$LG_HTTP_PORT}"; \
		export LOCAL_GAMMA_PRODUCT_OPS_BASE_URL="$${LOCAL_GAMMA_PRODUCT_OPS_BASE_URL:-http://127.0.0.1:$$LG_PRODUCT_OPS_PORT}"; \
		export LOCAL_GAMMA_MEDIA_BASE_URL="$${LOCAL_GAMMA_MEDIA_BASE_URL:-$$LOCAL_GAMMA_GATEWAY_BASE_URL}"; \
		if [ "$${LOCAL_GAMMA_SKIP_GATE:-0}" != "1" ]; then $(MAKE) gate; fi; \
		$(MAKE) verify-app-env-package; \
		$(MAKE) verify-app-seed-manifest; \
		bash quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh; \
		python3 quwoquan_app/scripts/gamma/run_local_gamma_t3.py; \
		bash quwoquan_app/scripts/gamma/run_local_gamma_t4.sh; \
		python3 quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py; \
	fi

gate-runtime-media:
	@bash agent_ops/gate/gate_runtime_media.sh

gate-runtime-media-full:
	@bash agent_ops/gate/gate_runtime_media.sh --full

# 群头像商用 E1–E4 证据机器校验（须先有 non-dry-run JSON，见 commercial-e2e-matrix-runbook.md）
verify-chat-avatar-commercial-matrix:
	@if [ -z "$(COMMERCIAL_MATRIX_MANIFEST)" ]; then \
		echo "FAIL: 请设置 COMMERCIAL_MATRIX_MANIFEST=artifacts/commercial-matrix/chat-avatar/manifest.yaml"; \
		exit 2; \
	fi
	@python3 agent_ops/avatar/verify_chat_avatar_commercial_matrix_evidence.py --manifest "$(COMMERCIAL_MATRIX_MANIFEST)"

run-chat-avatar-commercial-matrix-local:
	@bash agent_ops/avatar/run_chat_avatar_commercial_matrix_orchestrator.sh

verify:
	@bash agent_ops/scaffold/verify_feature_traceability.sh
	@bash quwoquan_service/scripts/contract/verify_contract_metadata.sh
	@bash agent_ops/scaffold/verify_acceptance_standard.sh
	@bash agent_ops/scaffold/verify_specs_l1_hierarchy.sh
	@bash agent_ops/scaffold/verify_feature_tree_refactor.sh
	@bash agent_ops/scaffold/verify_engineering_directory.sh
	@bash quwoquan_service/scripts/deploy/verify_opsx_ff_8services_consistency.sh
	@bash quwoquan_service/scripts/runtime/verify_runtime_packaging.sh
	@bash quwoquan_service/scripts/deploy/verify_ff_config_contract.sh
	@bash quwoquan_service/scripts/deploy/verify_deployment_domain_mapping.sh
	@$(MAKE) verify-reliable-task-topology
	@bash quwoquan_service/scripts/deploy/report_deployment_mapping_impact.sh
	@bash quwoquan_service/scripts/recommendation/verify_recommendation_service_contract.sh
	@bash quwoquan_service/scripts/deploy/verify_topology_contract_regression.sh
	@bash quwoquan_service/scripts/deploy/verify_config_gray_parallel_binding.sh
	@$(MAKE) verify-quwoquan-data

codegen:
	@$(MAKE) -C quwoquan_service codegen

codegen-app:
	@$(MAKE) -C quwoquan_service codegen-app

codegen-ops-portal:
	@$(MAKE) -C quwoquan_service codegen-ops-portal

codegen-control-plane-runtime:
	@$(MAKE) -C quwoquan_service codegen-control-plane-runtime

codegen-content-service:
	@$(MAKE) -C quwoquan_service codegen-content-service

# Bootstrap env-split config layout for a service.
# Usage:
#   make bootstrap-service-config SERVICE=content-service
bootstrap-service-config:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make bootstrap-service-config SERVICE=content-service"; \
		exit 2; \
	fi
	@bash quwoquan_service/scripts/runtime/bootstrap_service_config_layout.sh --service "$(SERVICE)"

# Create a new service scaffold and auto-bootstrap env-split config layout.
# Usage:
#   make new-service SERVICE=user-service PORT=18081
new-service:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make new-service SERVICE=user-service PORT=18081"; \
		exit 2; \
	fi
	@bash agent_ops/scaffold/new_service_fullstack.sh --name "$(SERVICE)" --port "$(if $(PORT),$(PORT),18080)"

# Progressive rollout state update for config release.
# Example:
# make config-gray-rollout SERVICE=content-service FROM_IMAGE=1.7.2 TO_IMAGE=1.8.0 FROM_CONFIG=v2026.02.27.1 TO_CONFIG=v2026.02.28.0 STEP=25
config-gray-rollout:
	@if [ -z "$(SERVICE)" ] || [ -z "$(FROM_IMAGE)" ] || [ -z "$(TO_IMAGE)" ] || [ -z "$(FROM_CONFIG)" ] || [ -z "$(TO_CONFIG)" ] || [ -z "$(STEP)" ]; then \
		echo "FAIL: SERVICE/FROM_IMAGE/TO_IMAGE/FROM_CONFIG/TO_CONFIG/STEP are required"; \
		exit 2; \
	fi
	@bash agent_ops/deploy/prod/config_release_gray_rollout.sh --service "$(SERVICE)" --from-image "$(FROM_IMAGE)" --to-image "$(TO_IMAGE)" --from-config "$(FROM_CONFIG)" --to-config "$(TO_CONFIG)" --step "$(STEP)"

# Idempotent rollback to a target config version.
# Example:
# make config-rollback SERVICE=content-service TO_CONFIG=v2026.02.27.1
config-rollback:
	@if [ -z "$(SERVICE)" ] || [ -z "$(TO_CONFIG)" ]; then \
		echo "FAIL: SERVICE and TO_CONFIG are required"; \
		exit 2; \
	fi
	@bash agent_ops/deploy/prod/config_release_rollback.sh --service "$(SERVICE)" --to-config-version "$(TO_CONFIG)"

# Evaluate SLO gate decision for a rollout stage.
# Example:
# make config-slo-gate ERROR_RATE=0.005 P95_MS=180 REDIS_ERROR_RATE=0.001
config-slo-gate:
	@if [ -z "$(ERROR_RATE)" ] || [ -z "$(P95_MS)" ] || [ -z "$(REDIS_ERROR_RATE)" ]; then \
		echo "FAIL: ERROR_RATE/P95_MS/REDIS_ERROR_RATE are required"; \
		exit 2; \
	fi
	@bash agent_ops/deploy/prod/config_release_slo_gate.sh --error-rate "$(ERROR_RATE)" --p95-ms "$(P95_MS)" --redis-error-rate "$(REDIS_ERROR_RATE)"

.PHONY: l2-content gate-full test-api-contract test-api-contract-chat gamma-validate-smoke-full gamma-validate-ui-full gamma-validate-full

# 本地 L2 契约测试（content-service，需 MongoDB 在 localhost:27017）
# 提交前运行以避免 CI 失败。详见 .cursor/rules/03-testing.mdc §2.1
l2-content:
	@bash quwoquan_app/scripts/content/run_l2_content_tests.sh

# L3：按统一环境名解析 HTTP 基址。API_CONTRACT_ENV 默认为 gamma。
# 变量格式：{ALPHA|BETA|GAMMA|PROD_GRAY|PROD}_BASE_URL 与 *_PRODUCT_OPS_BASE_URL。
test-api-contract:
	@ENV_NAME="$${API_CONTRACT_ENV:-gamma}"; \
	case "$$ENV_NAME" in \
		alpha) BASE_URL="$${ALPHA_BASE_URL:-}"; OPS_BASE_URL="$${ALPHA_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${ALPHA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		beta) BASE_URL="$${BETA_BASE_URL:-}"; OPS_BASE_URL="$${BETA_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${BETA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		gamma) BASE_URL="$${GAMMA_BASE_URL:-}"; OPS_BASE_URL="$${GAMMA_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		prod-gray) BASE_URL="$${PROD_GRAY_BASE_URL:-}"; OPS_BASE_URL="$${PROD_GRAY_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${PROD_GRAY_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		prod) BASE_URL="$${PROD_BASE_URL:-}"; OPS_BASE_URL="$${PROD_PRODUCT_OPS_BASE_URL:-}"; AUTH_TOKEN="$${PROD_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		*) echo "[L3] FAIL: API_CONTRACT_ENV must be one of alpha|beta|gamma|prod-gray|prod, got $$ENV_NAME"; exit 2 ;; \
	esac; \
	if [ -z "$$BASE_URL" ] || [ -z "$$OPS_BASE_URL" ]; then \
		echo "[L3] FAIL: set $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_BASE_URL and $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_PRODUCT_OPS_BASE_URL"; \
		exit 2; \
	fi; \
	cd quwoquan_app && flutter test test/cloud/content/api_contract_runner.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL \
		--dart-define=LOCAL_GAMMA_T3_SCOPE=$${LOCAL_GAMMA_T3_SCOPE:-} \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN && \
	flutter test test/cloud/ops/api_contract_runner.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL=$$OPS_BASE_URL

test-api-contract-chat:
	@ENV_NAME="$${API_CONTRACT_ENV:-gamma}"; \
	case "$$ENV_NAME" in \
		alpha) BASE_URL="$${ALPHA_BASE_URL:-}"; AUTH_TOKEN="$${ALPHA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		beta) BASE_URL="$${BETA_BASE_URL:-}"; AUTH_TOKEN="$${BETA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		gamma) BASE_URL="$${GAMMA_BASE_URL:-}"; AUTH_TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		prod-gray) BASE_URL="$${PROD_GRAY_BASE_URL:-}"; AUTH_TOKEN="$${PROD_GRAY_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		prod) BASE_URL="$${PROD_BASE_URL:-}"; AUTH_TOKEN="$${PROD_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}" ;; \
		*) echo "[L3] FAIL: API_CONTRACT_ENV must be one of alpha|beta|gamma|prod-gray|prod, got $$ENV_NAME"; exit 2 ;; \
	esac; \
	if [ -z "$$BASE_URL" ]; then \
		echo "[L3] FAIL: set $$(printf '%s' "$$ENV_NAME" | tr '[:lower:]-' '[:upper:]_')_BASE_URL"; \
		exit 2; \
	fi; \
	cd quwoquan_app && flutter test test/cloud/chat/api_contract_runner.dart \
		--dart-define=API_CONTRACT_ENV=$$ENV_NAME \
		--dart-define=API_CONTRACT_BASE_URL=$$BASE_URL \
		--dart-define=TEST_AUTH_TOKEN=$$AUTH_TOKEN

# gate-full: L1+L2+L3（daily CI / pre-release）
# PR 日常开发用 make gate；pre-release 用 make gate-full。
gate-full:
	@bash agent_ops/gate/gate_repo.sh
	@if [ -n "$${GAMMA_BASE_URL:-}" ] && [ -n "$${GAMMA_PRODUCT_OPS_BASE_URL:-}" ]; then \
		$(MAKE) test-api-contract; \
	else \
		echo "[gate-full] GAMMA_* not set; running local gamma T3/T4 mirror gate"; \
		$(MAKE) gate-local-gamma LOCAL_GAMMA_SKIP_GATE=1; \
	fi

gamma-validate-smoke-full:
	@TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}"; \
	if [ -z "$${GAMMA_BASE_URL:-}" ] || [ -z "$${GAMMA_PRODUCT_OPS_BASE_URL:-}" ] || [ -z "$$TOKEN" ]; then \
		echo "FAIL: GAMMA_BASE_URL / GAMMA_PRODUCT_OPS_BASE_URL / GAMMA_TEST_AUTH_TOKEN(or TEST_AUTH_TOKEN) are required"; \
		exit 2; \
	fi; \
	python3 quwoquan_service/scripts/gamma/verify_gamma_environment_ready.py \
		--base-url "$${GAMMA_BASE_URL}" \
		--product-ops-base-url "$${GAMMA_PRODUCT_OPS_BASE_URL}" \
		--report artifacts/gamma-validation/smoke/readiness.json && \
	( \
		cd quwoquan_app && \
		flutter pub get && \
		flutter test test/common/assistant/assistant_environment_smoke_test.dart \
			--dart-define=APP_RUNTIME_ENV=gamma \
			--dart-define=APP_DATA_SOURCE=remote \
			--dart-define=CLOUD_GATEWAY_BASE_URL="$${GAMMA_BASE_URL}" \
			--dart-define=ASSISTANT_SMOKE_PROFILE=full_semantic \
			--dart-define=ASSISTANT_SMOKE_MAX_TICKS=$${ASSISTANT_SMOKE_MAX_TICKS:-1500} \
			--dart-define=ASSISTANT_SMOKE_MAX_IDLE_TICKS=$${ASSISTANT_SMOKE_MAX_IDLE_TICKS:-180} \
	) && \
	python3 agent_ops/avatar/run_chat_avatar_e2e_probe.py \
		--env cloud-gamma-full \
		--base-url "$${GAMMA_BASE_URL}" \
		--media-base-url "$${MEDIA_AVATAR_CDN_BASE_URL:-$${GAMMA_BASE_URL}}" \
		--test-auth-token "$$TOKEN" \
		--report artifacts/gamma-validation/smoke/chat_avatar_api_probe.json

gamma-validate-ui-full:
	@TOKEN="$${GAMMA_TEST_AUTH_TOKEN:-$${TEST_AUTH_TOKEN:-}}"; \
	if [ -z "$${GAMMA_BASE_URL:-}" ] || [ -z "$${GAMMA_PRODUCT_OPS_BASE_URL:-}" ] || [ -z "$$TOKEN" ]; then \
		echo "FAIL: GAMMA_BASE_URL / GAMMA_PRODUCT_OPS_BASE_URL / GAMMA_TEST_AUTH_TOKEN(or TEST_AUTH_TOKEN) are required"; \
		exit 2; \
	fi; \
	python3 quwoquan_service/scripts/gamma/verify_gamma_environment_ready.py \
		--base-url "$${GAMMA_BASE_URL}" \
		--product-ops-base-url "$${GAMMA_PRODUCT_OPS_BASE_URL}" \
		--report artifacts/gamma-validation/ui/readiness.json && \
	python3 agent_ops/deploy/gamma/run_gamma_patrol_profile.py \
		--profile "$${GAMMA_UI_PROFILE:-nightly_full}" \
		--report "artifacts/gamma-validation/ui/$${GAMMA_UI_PROFILE:-nightly_full}/report.json" \
		--gateway-base-url "$${GAMMA_BASE_URL}" \
		--product-ops-base-url "$${GAMMA_PRODUCT_OPS_BASE_URL}" \
		--test-auth-token "$$TOKEN" \
		--platform "$${GAMMA_UI_PLATFORM:-all}"

gamma-validate-full:
	@$(MAKE) gamma-validate-smoke-full
	@$(MAKE) gamma-validate-ui-full

# Deploy to beta/gamma integration K8s. CLOUD_PROVIDER=aliyun|volcengine|huaweicloud (default: aliyun).
# Usage: make deploy-beta-k8s [CLOUD_PROVIDER=volcengine]
#        make deploy-gamma-k8s [CLOUD_PROVIDER=volcengine]
.PHONY: deploy-beta-k8s deploy-gamma-k8s
deploy-beta-k8s:
	@bash agent_ops/deploy/beta/deploy_beta_k8s.sh
deploy-gamma-k8s:
	@bash agent_ops/deploy/gamma/deploy_gamma_k8s.sh

