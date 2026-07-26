SERVICE_ROOT := $(abspath ../..)
REPO_ROOT := $(abspath ../../..)
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
BUILD_OUTPUT_DIR := $(QWQ_OUTPUT_ROOT)/env/repo/local/service-build/cache/$(notdir $(CURDIR))
SERVICE_PACKAGE := ./services/realtime-gateway/internal/... ./services/realtime-gateway/cmd/... ./services/realtime-gateway/tests/...
COMMAND_PACKAGE := ./services/realtime-gateway/cmd/...

.PHONY: build test gate

build:
	@mkdir -p "$(BUILD_OUTPUT_DIR)"
	cd $(SERVICE_ROOT) && go build -o "$(BUILD_OUTPUT_DIR)/" $(COMMAND_PACKAGE)

test:
	cd $(SERVICE_ROOT) && \
		pkgs=$$(go list $(SERVICE_PACKAGE) | grep -v '/tests/api_integration' || true); \
		if [ -n "$$pkgs" ]; then go test $$pkgs -count=1; fi

gate: build test
