.PHONY: gate
.PHONY: verify
.PHONY: codegen-app
.PHONY: codegen-content-service

gate:
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

codegen-app:
	@$(MAKE) -C quwoquan_service codegen-app

codegen-content-service:
	@$(MAKE) -C quwoquan_service codegen-content-service

.PHONY: gate-full test-api-contract

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

