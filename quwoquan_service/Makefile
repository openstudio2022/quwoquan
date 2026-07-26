.PHONY: gate build test test-all-services test-unit test-contract test-contract-local test-integration test-runtime-api-integration test-chat-ready-index-alpha-beta lint service-contract-view verify-metadata verify-openapi verify-contract-graph verify-contract-graph-commercial verify-contract-graph-single-track verify-observability-catalog verify-assistant-service-errors verify-assistant-runtime-enums verify-content-service-codegen verify-entity-service-codegen verify-integration-service-codegen verify-external-provider-bindings verify-external-provider-governance verify-ddd-cqrs-baseline verify-codegen-contract-graph-source verify-go-single-module verify-service-layering verify-production-wiring-purity verify-content-architecture codegen codegen-openapi codegen-contract-graph codegen-observability-catalog codegen-app codegen-ops-portal codegen-control-plane-runtime codegen-assistant-service-errors codegen-assistant-runtime-enums codegen-external-provider-bindings codegen-content-service codegen-circle-service codegen-entity-service codegen-notification-service codegen-rtc-service codegen-realtime-gateway codegen-integration-service codegen-product-ops-service codegen-platform-ops-service codegen-user-service codegen-chat-service codegen-chat-domain-events codegen-rec-model-python codegen-rec-policy codegen-storage dev dev-down dev-redis dev-redis-down dev-reliable-task-local dev-reliable-task-local-down clean verify-ml-features verify-ml-model-quality verify-ml-e2e verify-ml-e2e-live verify-ml-guardrail verify-ml-drift verify-ml-tests verify-rec-policy-advisor verify-content-flywheel-tests verify-content-flywheel-loop
.PHONY: verify-assistant-citation-destinations codegen-assistant-citation-destinations

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
QWQ_OUTPUT_ROOT := $(REPO_ROOT)/.qwq_output
CONTRACT_VIEW ?= $(QWQ_OUTPUT_ROOT)/env/repo/local/service-contract-view/cache
ML_REPORT_ROOT ?= $(QWQ_OUTPUT_ROOT)/env/repo/runs/ml
QWQ_PYTHON_CACHE_ROOT ?= $(HOME)/.cache/quwoquan/python-envs
DATA_PYTHON ?= $(QWQ_PYTHON_CACHE_ROOT)/quwoquan-data/bin/python
ML_PYTHON ?= $(QWQ_PYTHON_CACHE_ROOT)/rec-model/bin/python
ML_SCRIPTS := services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts
PYTEST_FLAGS := -o cache_dir=$(QWQ_OUTPUT_ROOT)/env/repo/local/tests/cache/pytest
DOMAIN_SERVICES := assistant-service chat-service circle-service content-service entity-service integration-service notification-service product-ops-service realtime-gateway recommendation-service rtc-service search-service tag-service user-service
export QWQ_OUTPUT_ROOT
export PYTHONDONTWRITEBYTECODE ?= 1

# ─── Quality Gate ────────────────────────────────────────────────────
gate: verify-metadata verify-go-single-module verify-service-layering verify-production-wiring-purity
	@PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/gate/verify_service_architecture.py
	@set -e; for service in $(DOMAIN_SERVICES); do \
		echo "[gate] $$service"; \
		$(MAKE) -C "services/$$service" gate; \
	done

# ─── Build ───────────────────────────────────────────────────────────
build:
	go list ./... | awk '$$0 !~ /\/tests(\/|$$)/' | xargs go build

# ─── Test ────────────────────────────────────────────────────────────
test: test-all-services

test-all-services:
	@set -e; for service in $(DOMAIN_SERVICES); do \
		echo "[test] $$service"; \
		$(MAKE) -C "services/$$service" test; \
	done

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

test-integration: test-runtime-api-integration

test-runtime-api-integration:
	go test ./runtime/... -v -count=1 -tags=api_integration

test-chat-ready-index-alpha-beta:
	TEST_REDIS_ADDR=$${TEST_REDIS_ADDR:-localhost:6379} \
	TEST_MONGO_URI=$${TEST_MONGO_URI:-mongodb://localhost:27017/?replicaSet=rs0} \
	  go test ./runtime/reliabletask ./services/chat-service/tests -run 'TestRedisReadyIndexStandaloneStreamsClaimAck|TestGroupAvatar_RedisReadyIndexAlphaBetaLocalLoop' -v -count=1

# ─── Lint ────────────────────────────────────────────────────────────
lint:
	go vet ./runtime/...
	go vet ./tools/...

# ─── Metadata ────────────────────────────────────────────────────────
service-contract-view:
	@python3 scripts/contracts/build_service_contract_view.py --output "$(CONTRACT_VIEW)"

verify-ddd-cqrs-baseline:
	go test ./internal/metadata/load ./internal/metadata/graph ./internal/metadata/validate
	go test ./services/content-service/internal/trust_safety/report/domain/... ./services/content-service/internal/trust_safety/report/application

verify-metadata: service-contract-view verify-codegen-contract-graph-source verify-contract-graph-single-track verify-observability-catalog verify-assistant-service-errors verify-assistant-runtime-enums verify-assistant-citation-destinations verify-content-service-codegen verify-entity-service-codegen verify-integration-service-codegen verify-external-provider-bindings verify-external-provider-governance
	@$(MAKE) verify-contract-graph-commercial
	go run ./tools/verify_metadata/ "$(CONTRACT_VIEW)"

verify-observability-catalog: service-contract-view
	go run ./tools/codegen_observability_catalog --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)" --check

verify-assistant-service-errors: service-contract-view
	go run ./tools/codegen_service_errors --metadata-dir "$(CONTRACT_VIEW)" --domain assistant --output-root services/assistant-service/generated --check

verify-assistant-runtime-enums: service-contract-view
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --assistant-runtime-enums-go-output services/assistant-service/generated/assistant/assistant_conversation/assistant_runtime_enums.g.go --check-assistant-runtime-enums-go

verify-assistant-citation-destinations: service-contract-view
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --citation-destinations-go-output services/assistant-service/generated/assistant/assistant_conversation/citation_destinations.g.go --check-citation-destinations-go

verify-content-service-codegen: service-contract-view
	go run ./tools/codegen_content_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/content-service/generated --aggregate Post --route-service content-service --check

verify-entity-service-codegen: service-contract-view
	go run ./tools/codegen_entity_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/entity-service/generated --check

verify-integration-service-codegen: service-contract-view
	go run ./tools/codegen_integration_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/integration-service/generated --check

verify-external-provider-bindings:
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --quiet --go-bindings --check

verify-external-provider-governance:
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/gate/verify_external_provider_governance.py

verify-openapi: service-contract-view
	go run ./tools/qwq_contract check-openapi --metadata-dir "$(CONTRACT_VIEW)"

verify-contract-graph: verify-openapi
	go run ./tools/qwq_contract validate --metadata-dir "$(CONTRACT_VIEW)" --profile baseline
	go run ./tools/qwq_contract check --metadata-dir "$(CONTRACT_VIEW)" --profile baseline --input generated/contract_graph.json
	go run ./tools/qwq_contract coverage --metadata-dir "$(CONTRACT_VIEW)"

verify-contract-graph-commercial: verify-openapi
	go run ./tools/qwq_contract validate --metadata-dir "$(CONTRACT_VIEW)" --profile commercial
	go run ./tools/qwq_contract check --metadata-dir "$(CONTRACT_VIEW)" --profile commercial --input generated/contract_graph.json
	go run ./tools/qwq_contract coverage --metadata-dir "$(CONTRACT_VIEW)"

verify-contract-graph-single-track:
	python3 scripts/verify/verify_contract_graph_single_track.py

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

codegen: codegen-contract-graph codegen-observability-catalog codegen-assistant-service-errors codegen-assistant-runtime-enums codegen-assistant-citation-destinations codegen-external-provider-bindings codegen-content-service codegen-circle-service codegen-entity-service codegen-notification-service codegen-rtc-service codegen-realtime-gateway codegen-integration-service codegen-product-ops-service codegen-platform-ops-service codegen-user-service codegen-chat-service codegen-chat-domain-events codegen-storage codegen-rec-model-python codegen-rec-policy codegen-rec-intersection codegen-impact codegen-control-plane-runtime codegen-ops-portal

codegen-openapi: service-contract-view
	go run ./tools/qwq_contract generate-openapi --metadata-dir "$(CONTRACT_VIEW)"
	PYTHONDONTWRITEBYTECODE=1 python3 scripts/contracts/sync_service_openapi.py --contract-view "$(CONTRACT_VIEW)"

codegen-contract-graph: codegen-openapi
	go run ./tools/qwq_contract generate --metadata-dir "$(CONTRACT_VIEW)" --profile commercial --output generated/contract_graph.json --go-security-output generated/operationsecurity/descriptors.g.go

codegen-observability-catalog:
	go run ./tools/codegen_observability_catalog --metadata-dir "$(CONTRACT_VIEW)" --repo-root "$(REPO_ROOT)"

codegen-rec-intersection:
	go run ./tools/codegen_rec_intersection --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/content-service/generated/content/post

codegen-impact:
	go run ./tools/codegen_impact --metadata-dir "$(CONTRACT_VIEW)" --output-dir runtime/impact

codegen-app:
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --contract-graph generated/contract_graph.json --contract-graph-lock ../quwoquan_app/tool/cloud_codegen/contract_graph.lock.json --app-dir ../quwoquan_app --generated-manifest ../quwoquan_app/tool/cloud_codegen/generated_manifest.json

codegen-ops-portal:
	go run ./tools/codegen_ops_portal_metadata --metadata-dir "$(CONTRACT_VIEW)" --portal-dir ../quwoquan_ops/portal

codegen-control-plane-runtime:
	go run ./tools/codegen_control_plane_runtime --metadata-dir "$(CONTRACT_VIEW)" --go-out-dir ./generated/control_plane --python-out-dir ./services/recommendation-service/generated/recommendation/recommendation_model_release/control_plane

codegen-assistant-service-errors:
	go run ./tools/codegen_service_errors --metadata-dir "$(CONTRACT_VIEW)" --domain assistant --output-root services/assistant-service/generated

codegen-assistant-runtime-enums:
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --assistant-runtime-enums-go-output services/assistant-service/generated/assistant/assistant_conversation/assistant_runtime_enums.g.go

codegen-assistant-citation-destinations:
	go run ./tools/codegen_app_metadata --metadata-dir "$(CONTRACT_VIEW)" --citation-destinations-go-output services/assistant-service/generated/assistant/assistant_conversation/citation_destinations.g.go

codegen-external-provider-bindings:
	PYTHONDONTWRITEBYTECODE=1 python3 ../quwoquan_ops/cli/lib/external_provider_governance.py --quiet --go-bindings

codegen-content-service:
	go run ./tools/codegen_content_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/content-service/generated --aggregate Post --route-service content-service

codegen-circle-service:
	go run ./tools/codegen_circle_domain --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/circle-service/generated/circle_management

codegen-entity-service:
	go run ./tools/codegen_entity_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/entity-service/generated

codegen-notification-service:
	go run ./tools/codegen_notification_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/notification-service/generated/notification_delivery/notification

codegen-rtc-service:
	go run ./tools/codegen_rtc_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/rtc-service/generated/rtc/call_session

codegen-realtime-gateway:
	go run ./tools/codegen_realtime_gateway --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/realtime-gateway/generated/realtime/connection

codegen-integration-service:
	go run ./tools/codegen_integration_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/integration-service/generated

codegen-product-ops-service:
	go run ./tools/codegen_product_ops_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/product-ops-service/generated

codegen-platform-ops-service:
	go run ./tools/codegen_platform_ops_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir control-plane/platform-ops/generated/platform_ops/config_snapshot

codegen-user-service:
	go run ./tools/codegen_user_service --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/user-service/generated

codegen-chat-service:
	go run ./tools/codegen_chat_service --metadata-dir "$(CONTRACT_VIEW)" --contracts-dir services/chat-service/contracts --output-dir services/chat-service/generated

codegen-chat-domain-events:
	go run ./tools/codegen_chat_domain_events --metadata-dir "$(CONTRACT_VIEW)" --output-dir services/chat-service/generated/chat

codegen-rec-model-python:
	go run ./tools/codegen_rec_model_python --metadata-dir "$(CONTRACT_VIEW)" --service-dir recommendation/recommendation/recommendation_model_release --output-dir services/recommendation-service/generated/recommendation/recommendation_model_release

codegen-rec-policy:
	go run ./tools/codegen_rec_policy --source services/content-service/resources/policies/content/post/recommendation_policy.yaml --out-dir runtime/recpolicy

codegen-storage:
	@echo "=== codegen-storage: content-service ==="
	go run ./tools/codegen_storage --metadata-dir "$(CONTRACT_VIEW)" --service-dir services/content-service
	@echo "=== codegen-storage: user-service ==="
	go run ./tools/codegen_storage --metadata-dir "$(CONTRACT_VIEW)" --service-dir services/user-service
	@echo "=== codegen-storage: tag-service ==="
	go run ./tools/codegen_storage --metadata-dir "$(CONTRACT_VIEW)" --service-dir services/tag-service

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
	$(ML_PYTHON) -m pytest $(PYTEST_FLAGS) services/recommendation-service/tests/local_contract/recommendation/recommendation/recommendation_model_release -q

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
