SERVICE_ROOT := $(abspath ../..)
REPO_ROOT := $(abspath ../../..)
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
BUILD_OUTPUT_DIR := $(QWQ_OUTPUT_ROOT)/env/repo/local/service-build/cache/$(notdir $(CURDIR))
SERVICE_PACKAGE := ./services/integration-service/...
COMMAND_PACKAGE := ./services/integration-service/cmd/...
TEST_PACKAGE := ./services/integration-service/tests/...
<<<<<<< Updated upstream
CONTRACT_VIEW := $(SERVICE_ROOT)/../.qwq_output/env/repo/local/service-contract-view/cache/integration-service
=======
CONTRACT_VIEW ?= $(QWQ_OUTPUT_ROOT)/env/repo/local/service-contract-view/cache/$(shell printf %s "$$PPID")
>>>>>>> Stashed changes

.PHONY: build test verify-codegen gate

build:
	@mkdir -p "$(BUILD_OUTPUT_DIR)"
	cd $(SERVICE_ROOT) && go build -o "$(BUILD_OUTPUT_DIR)/" $(COMMAND_PACKAGE)

test:
	cd $(SERVICE_ROOT) && \
		pkgs=$$(go list $(TEST_PACKAGE) | grep -v '/tests/api_integration' || true); \
		if [ -n "$$pkgs" ]; then go test $$pkgs -count=1; fi

verify-codegen:
	$(MAKE) -C $(SERVICE_ROOT) service-contract-view CONTRACT_VIEW="$(CONTRACT_VIEW)"
	cd $(SERVICE_ROOT) && go run ./tools/codegen_integration_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/integration-service/generated --check
	cd $(SERVICE_ROOT) && PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --quiet --go-bindings --check

gate: verify-codegen build test
