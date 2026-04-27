.PHONY: gate
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
.PHONY: verify-app-session-b-legacy
.PHONY: verify-app-assistant-search-weak-typing-ratchet
.PHONY: verify-app-ui-app-data-source-mode-ratchet
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

verify-app-session-b-legacy:
	@python3 scripts/verify_session_b_legacy_governance.py

# 助手手写（排除 generated）+ search_repository：Map/dynamic 计数棘轮（见 specs/gates/assistant_search_weak_typing_governance.md）
verify-app-assistant-search-weak-typing-ratchet:
	@python3 scripts/verify_assistant_search_weak_typing_ratchet.py

gate:
	@bash scripts/verify_deployment_domain_mapping.sh
	@bash scripts/verify_topology_contract_regression.sh
	@bash scripts/report_deployment_mapping_impact.sh
	@bash scripts/gate_repo.sh

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

.PHONY: l2-content gate-full test-api-contract

# 本地 L2 契约测试（content-service，需 MongoDB 在 localhost:27017）
# 提交前运行以避免 CI 失败。详见 .cursor/rules/03-testing.mdc §2.1
l2-content:
	@bash scripts/run_l2_content_tests.sh

# L3：对 integration 的 HTTP 基址（历史变量名 STAGING_*；语义见 deploy/shared/environment_matrix.md）。
# 需 content + ops 两基址（STAGING_* 或 INTEGRATION_*）与 TEST_AUTH_TOKEN；缺则失败。
test-api-contract:
	@STAGING_BU="$${STAGING_BASE_URL:-$${INTEGRATION_BASE_URL}}"; \
	STAGING_OPS="$${STAGING_PRODUCT_OPS_BASE_URL:-$${INTEGRATION_PRODUCT_OPS_BASE_URL}}"; \
	if [ -z "$$STAGING_BU" ] || [ -z "$$STAGING_OPS" ]; then \
		echo "[L3] FAIL: set STAGING_BASE_URL+STAGING_PRODUCT_OPS_BASE_URL or INTEGRATION_BASE_URL+INTEGRATION_PRODUCT_OPS_BASE_URL"; \
		exit 2; \
	fi; \
	cd quwoquan_app && flutter test test/cloud/content/api_contract_runner.dart \
		--dart-define=STAGING_BASE_URL=$$STAGING_BU \
		--dart-define=TEST_AUTH_TOKEN=$(TEST_AUTH_TOKEN) && \
	cd quwoquan_app && flutter test test/cloud/ops/api_contract_runner.dart \
		--dart-define=STAGING_PRODUCT_OPS_BASE_URL=$$STAGING_OPS

# gate-full: L1+L2+L3（daily CI / pre-release）
# PR 日常开发用 make gate；pre-release 用 make gate-full。
gate-full:
	@bash scripts/gate_repo.sh
	@$(MAKE) test-api-contract

# Deploy to integration. CLOUD_PROVIDER=aliyun|volcengine|huaweicloud (default: aliyun).
# Usage: make deploy-integration [CLOUD_PROVIDER=volcengine]
.PHONY: deploy-integration
deploy-integration:
	@bash scripts/deploy_to_integration.sh

