SERVICE_ROOT := $(abspath ../..)
REPO_ROOT := $(abspath ../../..)
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
BUILD_OUTPUT_DIR := $(QWQ_OUTPUT_ROOT)/env/repo/local/service-build/cache/$(notdir $(CURDIR))
SERVICE_PACKAGE := ./services/entity-service/...
COMMAND_PACKAGE := ./services/entity-service/cmd/...
TEST_PACKAGE := ./services/entity-service/tests/...
CONTRACT_VIEW ?= $(QWQ_OUTPUT_ROOT)/env/repo/local/service-contract-view/cache/$(shell printf %s "$$PPID")

.PHONY: build test verify-codegen gate

build:
	@mkdir -p "$(BUILD_OUTPUT_DIR)"
	cd $(SERVICE_ROOT) && go build -o "$(BUILD_OUTPUT_DIR)/" $(COMMAND_PACKAGE)

test:
	cd $(SERVICE_ROOT) && \
		pkgs=$$(go list $(TEST_PACKAGE) | grep -v '/tests/api_integration' || true); \
		if [ -n "$$pkgs" ]; then go test $$pkgs -count=1; fi

verify-codegen:
	$(MAKE) -C $(SERVICE_ROOT) CONTRACT_VIEW="$(CONTRACT_VIEW)" service-contract-view
	cd $(SERVICE_ROOT) && go run ./tools/codegen_entity_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/entity-service/generated --check

gate: verify-codegen build test
