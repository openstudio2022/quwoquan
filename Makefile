.PHONY: gate
.PHONY: gate-local-gamma
.PHONY: gate-runtime-media
.PHONY: gate-runtime-media-full
.PHONY: verify-app-mock-isolation
.PHONY: verify-app-lib-no-test-import
.PHONY: verify-app-page-horizontal-quality
.PHONY: verify-app-page-abc-governance
.PHONY: verify-app-page-abc-governance-enforce-a
.PHONY: verify-app-page-abc-governance-enforce-b
.PHONY: verify-app-page-abc-governance-enforce-c
.PHONY: verify-app-page-abc-governance-enforce-all
.PHONY: verify-app-ui-map-literal-budget
.PHONY: verify-app-session-b-current
.PHONY: verify-app-assistant-search-weak-typing-ratchet
.PHONY: verify-retired-terms-zero
.PHONY: verify-app-ui-app-data-source-mode-ratchet
.PHONY: verify-app-seed-manifest
.PHONY: verify-business-env-data-inventory
.PHONY: verify-app-env-package
.PHONY: verify-service-env-package
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
	@python3 scripts/verify_ui_mock_isolation.py

verify-app-lib-test-only-symbols:
	@python3 scripts/verify_lib_no_test_only_symbols.py

# lib 不得 import test/ 树（见 specs/gates/mock_test_separation_roadmap.md）
verify-app-lib-no-test-import:
	@python3 scripts/verify_lib_no_import_test_tree.py

# UI 层 AppDataSourceMode.mock / appDataSourceModeProvider 引用棘轮（见 specs/gates/ui_app_data_source_mode_baseline.json）
verify-app-ui-app-data-source-mode-ratchet:
	@python3 scripts/verify_ui_app_data_source_mode_ratchet.py

verify-app-seed-manifest:
	@python3 scripts/verify_app_seed_manifests.py

verify-business-env-data-inventory:
	@python3 scripts/verify_business_env_data_inventory.py

verify-app-env-package:
	@bash scripts/build_app_env_package.sh --env alpha
	@bash scripts/build_app_env_package.sh --env beta
	@bash scripts/build_app_env_package.sh --env gamma
	@bash scripts/build_app_env_package.sh --env prod-gray
	@bash scripts/build_app_env_package.sh --env prod

verify-service-env-package:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make verify-service-env-package SERVICE=content-service"; \
		exit 2; \
	fi
	@bash scripts/build_service_env_package.sh --service "$(SERVICE)" --env alpha
	@bash scripts/build_service_env_package.sh --service "$(SERVICE)" --env beta
	@bash scripts/build_service_env_package.sh --service "$(SERVICE)" --env gamma
	@bash scripts/build_service_env_package.sh --service "$(SERVICE)" --env prod-gray
	@bash scripts/build_service_env_package.sh --service "$(SERVICE)" --env prod

observability-es-up:
	@python3 scripts/observability/es_cli.py up

observability-es-down:
	@python3 scripts/observability/es_cli.py down

observability-es-health:
	@python3 scripts/observability/es_cli.py health

observability-es-bootstrap:
	@python3 scripts/observability/es_cli.py bootstrap

observability-es-smoke:
	@python3 scripts/observability/es_cli.py smoke

verify-reliable-task-topology:
	@python3 scripts/verify_module_package_mapping.py
	@python3 scripts/verify_reliable_task_catalog.py
	@python3 scripts/verify_reliable_task_retention_policy.py
	@python3 scripts/verify_module_permission_scope.py
	@python3 scripts/verify_reliable_task_migration.py

build-app-env:
	@if [ -z "$(ENV)" ]; then \
		echo "FAIL: ENV is required. Example: make build-app-env ENV=beta"; \
		exit 2; \
	fi
	@bash scripts/build_app_env_package.sh --env "$(ENV)"

build-service-env:
	@if [ -z "$(SERVICE)" ] || [ -z "$(ENV)" ]; then \
		echo "FAIL: SERVICE and ENV are required. Example: make build-service-env SERVICE=content-service ENV=beta"; \
		exit 2; \
	fi
	@bash scripts/build_service_env_package.sh --service "$(SERVICE)" --env "$(ENV)"

test-app-alpha-seed:
	@cd quwoquan_app && flutter test test/cloud/services/contract_seeded_mock_repository_test.dart

test-app-beta-seed:
	@python3 scripts/run_app_alpha_beta_seed_matrix.py

# 页面横向质量：矩阵列合法 + 磁盘路径与矩阵一致 + P2 清单 ⊆（与 gate app 段同向子集）
verify-app-page-horizontal-quality:
	@python3 scripts/verify_page_horizontal_quality_matrix.py
	@python3 scripts/verify_page_matrix_scan_complete.py

# 页面 A/B/C 专项扫描（默认仅报告、exit 0；加 --enforce-* 见 specs/gates/page_abc_governance.md）
verify-app-page-abc-governance:
	@python3 scripts/verify_page_abc_governance.py

verify-app-page-abc-governance-enforce-a:
	@python3 scripts/verify_page_abc_governance.py --enforce-a

verify-app-page-abc-governance-enforce-b:
	@python3 scripts/verify_page_abc_governance.py --enforce-b

verify-app-page-abc-governance-enforce-c:
	@python3 scripts/verify_page_abc_governance.py --enforce-c

verify-app-page-abc-governance-enforce-all:
	@python3 scripts/verify_page_abc_governance.py --enforce-a --enforce-b --enforce-c

# UI 层 Map<String,dynamic> 字面量防回退（见 specs/gates/ui_map_literal_budget.json）
verify-app-ui-map-literal-budget:
	@python3 scripts/verify_ui_map_literal_budget.py

verify-app-session-b-current:
	@python3 scripts/verify_session_b_current_governance.py

verify-retired-terms-zero:
	@python3 scripts/verify_retired_terms_zero.py

# 助手手写（排除 generated）+ search_repository：Map/dynamic 计数棘轮（见 specs/gates/assistant_search_weak_typing_governance.md）
verify-app-assistant-search-weak-typing-ratchet:
	@python3 scripts/verify_assistant_search_weak_typing_ratchet.py

gate:
	@bash scripts/verify_deployment_domain_mapping.sh
	@bash scripts/verify_topology_contract_regression.sh
	@$(MAKE) verify-reliable-task-topology
	@bash scripts/report_deployment_mapping_impact.sh
	@bash scripts/gate_repo.sh

gate-local-gamma:
	@if [ "$${LOCAL_GAMMA_DRY_RUN:-0}" = "1" ]; then \
		python3 scripts/verify_local_gamma_mirror.py --dry-run; \
	else \
		if [ "$${LOCAL_GAMMA_SKIP_GATE:-0}" != "1" ]; then $(MAKE) gate; fi; \
		$(MAKE) verify-app-env-package; \
		$(MAKE) verify-app-seed-manifest; \
		bash scripts/start_local_gamma_mirror.sh; \
		python3 scripts/run_local_gamma_t3.py; \
		bash scripts/run_local_gamma_t4.sh; \
		python3 scripts/verify_local_gamma_mirror.py; \
	fi

gate-runtime-media:
	@bash scripts/gate_runtime_media.sh

gate-runtime-media-full:
	@bash scripts/gate_runtime_media.sh --full

verify:
	@bash scripts/verify_feature_traceability.sh
	@bash scripts/verify_contract_metadata.sh
	@bash scripts/verify_acceptance_standard.sh
	@bash scripts/verify_specs_l1_hierarchy.sh
	@bash scripts/verify_feature_tree_refactor.sh
	@bash scripts/verify_engineering_directory.sh
	@bash scripts/verify_opsx_ff_8services_consistency.sh
	@bash scripts/verify_runtime_packaging.sh
	@bash scripts/verify_ff_config_contract.sh
	@bash scripts/verify_deployment_domain_mapping.sh
	@$(MAKE) verify-reliable-task-topology
	@bash scripts/report_deployment_mapping_impact.sh
	@bash scripts/verify_recommendation_service_contract.sh
	@bash scripts/verify_topology_contract_regression.sh
	@bash scripts/verify_config_gray_parallel_binding.sh

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
	@bash scripts/bootstrap_service_config_layout.sh --service "$(SERVICE)"

# Create a new service scaffold and auto-bootstrap env-split config layout.
# Usage:
#   make new-service SERVICE=user-service PORT=18081
new-service:
	@if [ -z "$(SERVICE)" ]; then \
		echo "FAIL: SERVICE is required. Example: make new-service SERVICE=user-service PORT=18081"; \
		exit 2; \
	fi
	@bash scripts/new_service_fullstack.sh --name "$(SERVICE)" --port "$(if $(PORT),$(PORT),18080)"

# Progressive rollout state update for config release.
# Example:
# make config-gray-rollout SERVICE=content-service FROM_IMAGE=1.7.2 TO_IMAGE=1.8.0 FROM_CONFIG=v2026.02.27.1 TO_CONFIG=v2026.02.28.0 STEP=25
config-gray-rollout:
	@if [ -z "$(SERVICE)" ] || [ -z "$(FROM_IMAGE)" ] || [ -z "$(TO_IMAGE)" ] || [ -z "$(FROM_CONFIG)" ] || [ -z "$(TO_CONFIG)" ] || [ -z "$(STEP)" ]; then \
		echo "FAIL: SERVICE/FROM_IMAGE/TO_IMAGE/FROM_CONFIG/TO_CONFIG/STEP are required"; \
		exit 2; \
	fi
	@bash scripts/config_release_gray_rollout.sh --service "$(SERVICE)" --from-image "$(FROM_IMAGE)" --to-image "$(TO_IMAGE)" --from-config "$(FROM_CONFIG)" --to-config "$(TO_CONFIG)" --step "$(STEP)"

# Idempotent rollback to a target config version.
# Example:
# make config-rollback SERVICE=content-service TO_CONFIG=v2026.02.27.1
config-rollback:
	@if [ -z "$(SERVICE)" ] || [ -z "$(TO_CONFIG)" ]; then \
		echo "FAIL: SERVICE and TO_CONFIG are required"; \
		exit 2; \
	fi
	@bash scripts/config_release_rollback.sh --service "$(SERVICE)" --to-config-version "$(TO_CONFIG)"

# Evaluate SLO gate decision for a rollout stage.
# Example:
# make config-slo-gate ERROR_RATE=0.005 P95_MS=180 REDIS_ERROR_RATE=0.001
config-slo-gate:
	@if [ -z "$(ERROR_RATE)" ] || [ -z "$(P95_MS)" ] || [ -z "$(REDIS_ERROR_RATE)" ]; then \
		echo "FAIL: ERROR_RATE/P95_MS/REDIS_ERROR_RATE are required"; \
		exit 2; \
	fi
	@bash scripts/config_release_slo_gate.sh --error-rate "$(ERROR_RATE)" --p95-ms "$(P95_MS)" --redis-error-rate "$(REDIS_ERROR_RATE)"

.PHONY: l2-content gate-full test-api-contract test-api-contract-chat

# 本地 L2 契约测试（content-service，需 MongoDB 在 localhost:27017）
# 提交前运行以避免 CI 失败。详见 .cursor/rules/03-testing.mdc §2.1
l2-content:
	@bash scripts/run_l2_content_tests.sh

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
	cd quwoquan_app && flutter test test/cloud/ops/api_contract_runner.dart \
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
	@bash scripts/gate_repo.sh
	@if [ -n "$${GAMMA_BASE_URL:-}" ] && [ -n "$${GAMMA_PRODUCT_OPS_BASE_URL:-}" ]; then \
		$(MAKE) test-api-contract; \
	else \
		echo "[gate-full] GAMMA_* not set; running local gamma T3/T4 mirror gate"; \
		$(MAKE) gate-local-gamma LOCAL_GAMMA_SKIP_GATE=1; \
	fi

# Deploy to integration. CLOUD_PROVIDER=aliyun|volcengine|huaweicloud (default: aliyun).
# Usage: make deploy-integration [CLOUD_PROVIDER=volcengine]
.PHONY: deploy-integration
deploy-integration:
	@bash scripts/deploy_to_integration.sh

