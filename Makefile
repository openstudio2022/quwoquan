.PHONY: gate
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

gate:
	@bash scripts/verify_deployment_domain_mapping.sh
	@bash scripts/verify_topology_contract_regression.sh
	@bash scripts/report_deployment_mapping_impact.sh
	@bash scripts/gate_repo.sh

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

# L3 API Contract runner (staging HTTP).
# Requires: STAGING_BASE_URL, TEST_AUTH_TOKEN env vars.
# staging 不可用时 skip + warn，不阻塞本地 gate。
test-api-contract:
	@if [ -z "$(STAGING_BASE_URL)" ]; then \
		echo "[L3] WARN: STAGING_BASE_URL not set — skipping api_contract tests"; \
		exit 0; \
	fi
	cd quwoquan_app && flutter test test/cloud/content/api_contract_runner.dart \
		--dart-define=STAGING_BASE_URL=$(STAGING_BASE_URL) \
		--dart-define=TEST_AUTH_TOKEN=$(TEST_AUTH_TOKEN)

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

