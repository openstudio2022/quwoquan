.PHONY: gate build test test-unit test-contract test-contract-local test-integration test-chat-ready-index-alpha-beta lint verify-metadata verify-openapi verify-contract-graph verify-contract-graph-commercial verify-registry-contract-graph-single-track verify-observability-catalog verify-assistant-service-errors verify-assistant-runtime-enums verify-external-provider-bindings verify-external-provider-governance verify-ddd-cqrs-baseline verify-codegen-contract-graph-source verify-go-single-module verify-service-layering verify-production-wiring-purity verify-content-architecture codegen codegen-openapi codegen-contract-graph codegen-observability-catalog codegen-app codegen-ops-portal codegen-control-plane-runtime codegen-assistant-service-errors codegen-assistant-runtime-enums codegen-external-provider-bindings codegen-content-service codegen-circle-service codegen-entity-service codegen-notification-service codegen-rtc-service codegen-realtime-gateway codegen-integration-service codegen-product-ops-service codegen-platform-ops-service codegen-user-service codegen-chat-service codegen-chat-domain-events codegen-rec-model-python codegen-rec-policy codegen-storage dev dev-down dev-redis dev-redis-down dev-reliable-task-local dev-reliable-task-local-down clean verify-ml-features verify-ml-model-quality verify-ml-e2e verify-ml-e2e-live verify-ml-guardrail verify-ml-drift verify-ml-tests verify-rec-policy-advisor verify-content-flywheel-tests verify-content-flywheel-loop

SCENARIO ?= content_feed
DB ?= quwoquan_content
MONGODB_URI ?= mongodb://127.0.0.1:27017/?directConnection=true
ML_DRY_RUN ?= false
ML_GUARDRAIL_ENV ?= gamma
ML_GUARDRAIL_WINDOW_HOURS ?= 4
ML_GUARDRAIL_DRY_RUN ?= true
ML_GUARDRAIL_OUT ?=
ML_DRIFT_BASELINE_DATE ?=
ML_DRIFT_OUT ?=
FLYWHEEL_REQUIRE_CLOSED ?= false
FLYWHEEL_OUT ?=
REPO_ROOT ?= $(abspath ..)
QWQ_OUTPUT_ROOT ?= $(REPO_ROOT)/.qwq_output
ML_REPORT_ROOT ?= $(QWQ_OUTPUT_ROOT)/env/repo/runs/ml
ML_PYTHON ?= $(if $(wildcard $(QWQ_OUTPUT_ROOT)/env/repo/local/python-envs/cache/rec-model/bin/python),$(QWQ_OUTPUT_ROOT)/env/repo/local/python-envs/cache/rec-model/bin/python,python3)
ML_SCRIPTS := services/rec-model-service/scripts
PYTEST_FLAGS := -o cache_dir=$(QWQ_OUTPUT_ROOT)/env/repo/local/tests/cache/pytest
export QWQ_OUTPUT_ROOT
export PYTHONDONTWRITEBYTECODE ?= 1

# ─── Quality Gate ────────────────────────────────────────────────────
gate:
	@bash scripts/gate.sh

# ─── Build ───────────────────────────────────────────────────────────
build:
	go list ./... | awk '$$0 !~ /\/tests(\/|$$)/' | xargs go build

# ─── Test ────────────────────────────────────────────────────────────
test: test-unit

test-unit:
	$(MAKE) -C services/assistant-service test
	go test ./runtime/... ./services/content-service/... ./services/chat-service/... ./services/user-service/... ./services/rtc-service/... -v -count=1

test-contract:
	$(MAKE) -C services/assistant-service test
	go test ./services/content-service/... ./services/chat-service/... ./services/user-service/... ./services/rtc-service/... -v -count=1

# Run L2 contract tests against a locally running MongoDB (no Docker required).
# Usage:
#   make test-contract-local                          # expects MongoDB at localhost:27017
#   make test-contract-local MONGO_PORT=27018         # custom port
#
# Quick start without Docker:
#   brew services start mongodb-community             # macOS via Homebrew
#   make test-contract-local
MONGO_PORT ?= 27017
test-contract-local:
	TEST_MONGO_URI=mongodb://localhost:$(MONGO_PORT) \
	  go test ./services/content-service/... -v -count=1 -timeout=60s

test-integration:
	go test ./runtime/... -v -count=1 -tags=integration

test-chat-ready-index-alpha-beta:
	TEST_REDIS_ADDR=$${TEST_REDIS_ADDR:-localhost:6379} \
	TEST_MONGO_URI=$${TEST_MONGO_URI:-mongodb://localhost:27017/?replicaSet=rs0} \
	  go test ./runtime/reliabletask ./services/chat-service/tests -run 'TestRedisReadyIndexStandaloneStreamsClaimAck|TestGroupAvatar_RedisReadyIndexAlphaBetaLocalLoop' -v -count=1

# ─── Lint ────────────────────────────────────────────────────────────
lint:
	go vet ./runtime/...
	go vet ./tools/...

# ─── Metadata ────────────────────────────────────────────────────────
verify-ddd-cqrs-baseline:
	go test ./internal/metadata/load ./internal/metadata/graph ./internal/metadata/validate
	go test ./services/content-service/internal/domain/report/... ./services/content-service/internal/application/report

verify-metadata: verify-codegen-contract-graph-source verify-registry-contract-graph-single-track verify-observability-catalog verify-assistant-service-errors verify-assistant-runtime-enums verify-external-provider-bindings verify-external-provider-governance
	@$(MAKE) verify-contract-graph-commercial
	go run ./tools/verify_metadata/ contracts/metadata

verify-observability-catalog:
	go run ./tools/codegen_observability_catalog --metadata-dir contracts/metadata --repo-root "$(REPO_ROOT)" --check

verify-assistant-service-errors:
	go run ./tools/codegen_service_errors --metadata-dir contracts/metadata --domain assistant --output services/assistant-service/internal/generated/errors.go --check

verify-assistant-runtime-enums:
	go run ./tools/codegen_app_metadata --metadata-dir contracts/metadata --assistant-runtime-enums-go-output services/assistant-service/internal/generated/assistant_runtime_enums.g.go --check-assistant-runtime-enums-go

verify-external-provider-bindings:
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner assistant-service --go-output services/assistant-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner integration-service --go-output services/integration-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner content-service --go-output services/content-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner user-service --go-output services/user-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner product-ops-service --go-output services/product-ops-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner rtc-service --go-output services/rtc-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner chat-service --go-output services/chat-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner circle-service --go-output services/circle-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner entity-service --go-output services/entity-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner notification-service --go-output services/notification-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner search-service --go-output services/search-service/internal/generated/external_provider_bindings.g.go --check
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner realtime-gateway --go-output services/realtime-gateway/internal/generated/external_provider_bindings.g.go --check

verify-external-provider-governance:
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/gate/verify_external_provider_governance.py

verify-openapi:
	go run ./tools/qwq_contract check-openapi --metadata-dir contracts/metadata

verify-contract-graph: verify-openapi
	go run ./tools/qwq_contract validate --metadata-dir contracts/metadata --profile baseline
	go run ./tools/qwq_contract check --metadata-dir contracts/metadata --profile baseline --input generated/contract_graph.json
	go run ./tools/qwq_contract coverage --metadata-dir contracts/metadata

verify-contract-graph-commercial: verify-openapi
	go run ./tools/qwq_contract validate --metadata-dir contracts/metadata --profile commercial
	go run ./tools/qwq_contract check --metadata-dir contracts/metadata --profile commercial --input generated/contract_graph.json
	go run ./tools/qwq_contract coverage --metadata-dir contracts/metadata

verify-registry-contract-graph-single-track:
	python3 scripts/verify/verify_registry_contract_graph_single_track.py

verify-codegen-contract-graph-source:
	python3 scripts/verify/verify_codegen_contract_graph_source.py

verify-go-single-module:
	python3 scripts/verify/verify_go_single_module.py

verify-service-layering:
	python3 scripts/verify/verify_service_layering.py

verify-production-wiring-purity:
	python3 scripts/verify/verify_production_wiring_purity.py

verify-content-architecture:
	python3 scripts/verify/verify_content_application_boundaries.py

codegen: codegen-contract-graph codegen-observability-catalog codegen-assistant-service-errors codegen-assistant-runtime-enums codegen-external-provider-bindings codegen-content-service codegen-circle-service codegen-entity-service codegen-notification-service codegen-rtc-service codegen-realtime-gateway codegen-integration-service codegen-product-ops-service codegen-platform-ops-service codegen-user-service codegen-chat-service codegen-chat-domain-events codegen-storage codegen-rec-model-python codegen-rec-policy codegen-rec-intersection codegen-impact codegen-control-plane-runtime codegen-ops-portal

codegen-openapi:
	go run ./tools/qwq_contract generate-openapi --metadata-dir contracts/metadata

codegen-contract-graph: codegen-openapi
	go run ./tools/qwq_contract generate --metadata-dir contracts/metadata --profile commercial --output generated/contract_graph.json --go-security-output generated/operationsecurity/descriptors.g.go

codegen-observability-catalog:
	go run ./tools/codegen_observability_catalog --metadata-dir contracts/metadata --repo-root "$(REPO_ROOT)"

codegen-rec-intersection:
	go run ./tools/codegen_rec_intersection --metadata-dir contracts/metadata --output-dir services/content-service/internal/generated

codegen-impact:
	go run ./tools/codegen_impact --metadata-dir contracts/metadata --output-dir runtime/impact

codegen-app:
	go run ./tools/codegen_app_metadata --metadata-dir contracts/metadata --contract-graph generated/contract_graph.json --contract-graph-lock ../quwoquan_app/tool/cloud_codegen/contract_graph.lock.json --app-dir ../quwoquan_app --generated-manifest ../quwoquan_app/tool/cloud_codegen/generated_manifest.json

codegen-ops-portal:
	go run ./tools/codegen_ops_portal_metadata --metadata-dir contracts/metadata --portal-dir ../quwoquan_ops/portal

codegen-control-plane-runtime:
	go run ./tools/codegen_control_plane_runtime --metadata-dir contracts/metadata --go-out-dir ./generated/control_plane --python-out-dir ./services/rec-model-service/generated/control_plane

codegen-assistant-service-errors:
	go run ./tools/codegen_service_errors --metadata-dir contracts/metadata --domain assistant --output services/assistant-service/internal/generated/errors.go

codegen-assistant-runtime-enums:
	go run ./tools/codegen_app_metadata --metadata-dir contracts/metadata --assistant-runtime-enums-go-output services/assistant-service/internal/generated/assistant_runtime_enums.g.go

codegen-external-provider-bindings:
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner assistant-service --go-output services/assistant-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner integration-service --go-output services/integration-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner content-service --go-output services/content-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner user-service --go-output services/user-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner product-ops-service --go-output services/product-ops-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner rtc-service --go-output services/rtc-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner chat-service --go-output services/chat-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner circle-service --go-output services/circle-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner entity-service --go-output services/entity-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner notification-service --go-output services/notification-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner search-service --go-output services/search-service/internal/generated/external_provider_bindings.g.go
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --descriptor-owner realtime-gateway --go-output services/realtime-gateway/internal/generated/external_provider_bindings.g.go

codegen-content-service:
	go run ./tools/codegen_content_service --metadata-dir contracts/metadata --output-dir services/content-service/internal --aggregate Post --route-service content-service

codegen-circle-service:
	go run ./tools/codegen_circle_domain --metadata-dir contracts/metadata --output-dir services/circle-service/internal

codegen-entity-service:
	go run ./tools/codegen_entity_service --metadata-dir contracts/metadata --output-dir services/entity-service/internal

codegen-notification-service:
	go run ./tools/codegen_notification_service --metadata-dir contracts/metadata --output-dir services/notification-service/internal

codegen-rtc-service:
	go run ./tools/codegen_rtc_service --metadata-dir contracts/metadata --output-dir services/rtc-service/internal

codegen-realtime-gateway:
	go run ./tools/codegen_realtime_gateway --metadata-dir contracts/metadata --output-dir services/realtime-gateway/internal

codegen-integration-service:
	go run ./tools/codegen_integration_service --metadata-dir contracts/metadata --output-dir services/integration-service/internal

codegen-product-ops-service:
	go run ./tools/codegen_product_ops_service --metadata-dir contracts/metadata --output-dir services/product-ops-service/internal

codegen-platform-ops-service:
	go run ./tools/codegen_platform_ops_service --metadata-dir contracts/metadata --output-dir services/platform-ops-service/internal

codegen-user-service:
	go run ./tools/codegen_user_service --metadata-dir contracts/metadata --output-dir services/user-service/internal

codegen-chat-service:
	go run ./tools/codegen_chat_service --metadata-dir contracts/metadata --output-dir services/chat-service/internal --manifest services/chat-service/codegen_chat_service_manifest.yaml

codegen-chat-domain-events:
	go run ./tools/codegen_chat_domain_events --metadata-dir contracts/metadata --output-dir services/chat-service/internal

codegen-rec-model-python:
	go run ./tools/codegen_rec_model_python --metadata-dir contracts/metadata --service-dir recommendation/model_release --output-dir services/rec-model-service/generated

codegen-rec-policy:
	go run ./tools/codegen_rec_policy --metadata-dir contracts/metadata --out-dir runtime/recpolicy

codegen-storage:
	@echo "=== codegen-storage: user-service ==="
	go run ./tools/codegen_storage --metadata-dir contracts/metadata --manifest services/user-service/codegen_storage_manifest.yaml

# ─── Dev Environment ─────────────────────────────────────────────────
dev:
	docker compose -f ../quwoquan_ops/environments/compose/docker-compose.yaml up -d
	@echo "Waiting for services..."
	@sleep 5
	@docker compose -f ../quwoquan_ops/environments/compose/docker-compose.yaml ps

dev-down:
	docker compose -f ../quwoquan_ops/environments/compose/docker-compose.yaml down -v

dev-redis:
	docker compose -f ../quwoquan_ops/environments/compose/docker-compose.local-redis.yml up -d
	@docker compose -f ../quwoquan_ops/environments/compose/docker-compose.local-redis.yml ps

dev-redis-down:
	docker compose -f ../quwoquan_ops/environments/compose/docker-compose.local-redis.yml down

dev-reliable-task-local: dev-redis

dev-reliable-task-local-down: dev-redis-down

# ─── Clean ───────────────────────────────────────────────────────────
clean:
	go clean -testcache
	rm -rf tmp/

# ─── ML Verification ────────────────────────────────────────────────
verify-ml-features:
	$(ML_PYTHON) $(ML_SCRIPTS)/verify_feature_consistency.py

verify-ml-tests:
	$(ML_PYTHON) -m pytest $(PYTEST_FLAGS) services/rec-model-service/tests -q

verify-rec-policy-advisor:
	$(ML_PYTHON) -m pytest $(PYTEST_FLAGS) scripts/recommendation/test_rec_policy_advisor.py -q

verify-content-flywheel-tests:
	$(ML_PYTHON) -m pytest $(PYTEST_FLAGS) scripts/recommendation/test_eval_content_flywheel_loop.py -q

verify-content-flywheel-loop:
	$(ML_PYTHON) scripts/recommendation/eval_content_flywheel_loop.py --mongodb-uri "$(MONGODB_URI)" $(if $(filter 1 true yes,$(FLYWHEEL_REQUIRE_CLOSED)),--require-closed-loop,) $(if $(strip $(FLYWHEEL_OUT)),--output "$(FLYWHEEL_OUT)",)

verify-ml-model-quality:
	@mkdir -p "$(ML_REPORT_ROOT)"
	$(ML_PYTHON) $(ML_SCRIPTS)/evaluate_gate.py --scenario "$(SCENARIO)" $(if $(filter 1 true yes,$(ML_DRY_RUN)),--dry-run,) --out "$(ML_REPORT_ROOT)/eval_report_$(SCENARIO).json"
	$(ML_PYTHON) $(ML_SCRIPTS)/evaluate_gate.py --scenario "$(SCENARIO)_multiobjective" $(if $(filter 1 true yes,$(ML_DRY_RUN)),--dry-run,) --out "$(ML_REPORT_ROOT)/eval_report_$(SCENARIO)_multiobjective.json"

verify-ml-e2e:
	$(ML_PYTHON) $(ML_SCRIPTS)/e2e_learning_loop_verify.py --scenario "$(SCENARIO)" --full-pipeline $(if $(strip $(REC_MODEL_URL)),--rec-model $(REC_MODEL_URL),--skip-service)

verify-ml-e2e-live:
	@test -n "$(strip $(REC_MODEL_URL))" || (echo "REC_MODEL_URL is required for verify-ml-e2e-live" >&2; exit 1)
	$(ML_PYTHON) $(ML_SCRIPTS)/e2e_learning_loop_verify.py --scenario "$(SCENARIO)" --mongodb-uri "$(MONGODB_URI)" --db "$(DB)" --rec-model "$(REC_MODEL_URL)"

verify-ml-guardrail:
	$(ML_PYTHON) $(ML_SCRIPTS)/online_guardrail.py --scenario "$(SCENARIO)" --window-hours "$(ML_GUARDRAIL_WINDOW_HOURS)" --env "$(ML_GUARDRAIL_ENV)" $(if $(filter 1 true yes,$(ML_GUARDRAIL_DRY_RUN)),--dry-run,) $(if $(strip $(ML_GUARDRAIL_OUT)),--out "$(ML_GUARDRAIL_OUT)",)

verify-ml-drift:
	$(ML_PYTHON) $(ML_SCRIPTS)/feature_drift_monitor.py --scenario "$(SCENARIO)" --baseline-date "$(ML_DRIFT_BASELINE_DATE)" $(if $(strip $(ML_DRIFT_OUT)),--out "$(ML_DRIFT_OUT)",)
