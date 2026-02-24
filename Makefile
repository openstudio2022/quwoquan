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

.PHONY: gate-full

gate-full:
	@QWQ_GATE_TESTS=1 bash scripts/gate_repo.sh

