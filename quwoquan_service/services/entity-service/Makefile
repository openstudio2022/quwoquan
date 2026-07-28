SERVICE_ROOT := $(abspath ../..)
REPO_ROOT := $(abspath ../../..)
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
BUILD_OUTPUT_DIR := $(QWQ_OUTPUT_ROOT)/env/repo/local/service-build/cache/$(notdir $(CURDIR))
SERVICE_PACKAGE := ./services/entity-service/...
COMMAND_PACKAGE := ./services/entity-service/cmd/...
TEST_PACKAGE := ./services/entity-service/tests/...
CONTRACT_VIEW := $(SERVICE_ROOT)/../.qwq_output/env/repo/local/service-contract-view/cache/entity-service

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
	cd $(SERVICE_ROOT) && go run ./tools/codegen_entity_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/entity-service/generated --check

gate: verify-codegen build test
