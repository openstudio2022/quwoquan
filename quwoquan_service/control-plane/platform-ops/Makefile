SERVICE_ROOT := $(abspath ../..)
REPO_ROOT := $(abspath ../../..)
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
BUILD_OUTPUT_DIR := $(QWQ_OUTPUT_ROOT)/env/repo/local/service-build/cache/$(notdir $(CURDIR))
COMMAND_PACKAGE := ./control-plane/platform-ops/cmd/...
LOCAL_CONTRACT_PACKAGE := ./control-plane/platform-ops/tests/local_contract/...
API_INTEGRATION_PACKAGE := ./control-plane/platform-ops/tests/api_integration/...
HUMAN_CONTRACT_SOURCE := ../quwoquan_ops/policies/human_agent_delivery_contract.yaml
HUMAN_CONTRACT_GENERATOR := control-plane/platform-ops/contracts/platform_ops/human_authority/generate_binding.py
HUMAN_AUTHORITY_FIELDS_SOURCE := control-plane/platform-ops/contracts/platform_ops/human_authority/fields.yaml
HUMAN_CONTRACT_OUTPUT := control-plane/platform-ops/internal/platform_ops/human_authority/domain/model/human_contract_generated.go

.PHONY: build test gate verify-human-contract-binding codegen-human-contract-binding test-local-contract test-api-integration

build:
	@mkdir -p "$(BUILD_OUTPUT_DIR)"
	cd $(SERVICE_ROOT) && go build -o "$(BUILD_OUTPUT_DIR)/" $(COMMAND_PACKAGE)

verify-human-contract-binding:
	cd $(SERVICE_ROOT) && PYTHONDONTWRITEBYTECODE=1 python3 $(HUMAN_CONTRACT_GENERATOR) \
		--source $(HUMAN_CONTRACT_SOURCE) \
		--fields-source $(HUMAN_AUTHORITY_FIELDS_SOURCE) \
		--output $(HUMAN_CONTRACT_OUTPUT) --check

codegen-human-contract-binding:
	cd $(SERVICE_ROOT) && PYTHONDONTWRITEBYTECODE=1 python3 $(HUMAN_CONTRACT_GENERATOR) \
		--source $(HUMAN_CONTRACT_SOURCE) \
		--fields-source $(HUMAN_AUTHORITY_FIELDS_SOURCE) \
		--output $(HUMAN_CONTRACT_OUTPUT)
	cd $(SERVICE_ROOT) && gofmt -w $(HUMAN_CONTRACT_OUTPUT)

test-local-contract:
	cd $(SERVICE_ROOT) && go test $(LOCAL_CONTRACT_PACKAGE) -count=1

test-api-integration:
	@set -eu; \
	log_file="$$(mktemp "$${TMPDIR:-/tmp}/qwq-human-authority-api-integration.XXXXXX")"; \
	trap 'rm -f "$$log_file"' EXIT; \
	cd $(SERVICE_ROOT); \
	test_status=0; \
	go test -json $(API_INTEGRATION_PACKAGE) -count=1 >"$$log_file" 2>&1 || test_status=$$?; \
	python3 -c 'import sys; sys.stdout.write(open(sys.argv[1], encoding="utf-8").read())' "$$log_file"; \
	if [ "$$test_status" -ne 0 ]; then exit "$$test_status"; fi; \
	python3 -c 'import json,sys; rows=[json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]; skipped=sorted({row.get("Test", "") for row in rows if row.get("Action") == "skip" and row.get("Test")}); print("[platform-ops] GATE_BLOCK: PostgreSQL prerequisite unavailable; skipped=" + ",".join(skipped), file=sys.stderr) if skipped else None; raise SystemExit(2 if skipped else 0)' "$$log_file"

test: verify-human-contract-binding test-local-contract

gate: build test
