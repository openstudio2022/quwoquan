.PHONY: gate build test test-unit test-contract test-contract-local test-integration test-chat-ready-index-alpha-beta lint verify-metadata codegen codegen-app codegen-ops-portal codegen-control-plane-runtime codegen-content-service codegen-circle-service codegen-rec-model-python codegen-storage dev dev-down dev-redis dev-redis-down dev-reliable-task-local dev-reliable-task-local-down clean verify-ml-features verify-ml-model-quality verify-ml-e2e verify-ml-e2e-live verify-ml-guardrail verify-ml-drift verify-ml-tests

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
ML_PYTHON ?= $(if $(wildcard services/rec-model-service/.venv/bin/python),services/rec-model-service/.venv/bin/python,python3)

# ─── Quality Gate ────────────────────────────────────────────────────
gate:
	@bash scripts/gate.sh

# ─── Build ───────────────────────────────────────────────────────────
build:
	go build ./runtime/...
	go build ./tools/...
	go build ./services/user-service/...
	go build ./services/rtc-service/...
	$(MAKE) -C services/assistant-service build

# ─── Test ────────────────────────────────────────────────────────────
test: test-unit

test-unit:
	$(MAKE) -C services/assistant-service test
	go test ./runtime/... ./generated/assistant/wirepoc/... ./services/content-service/... ./services/chat-service/... ./services/user-service/... ./services/rtc-service/... -v -count=1

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
verify-metadata:
	go run ./tools/verify_metadata/ contracts/metadata

codegen: codegen-content-service codegen-circle-service codegen-storage codegen-rec-model-python codegen-control-plane-runtime codegen-ops-portal

codegen-app:
	go run ./tools/codegen_app_metadata --metadata-dir contracts/metadata --app-dir ../quwoquan_app --integration-service-dir ./services/integration-service

codegen-ops-portal:
	go run ./tools/codegen_ops_portal_metadata --metadata-dir contracts/metadata --portal-dir ../apps/ops-portal

codegen-control-plane-runtime:
	go run ./tools/codegen_control_plane_runtime --metadata-dir contracts/metadata --go-out-dir ./generated/control_plane --python-out-dir ./services/rec-model-service/generated/control_plane

codegen-content-service:
	go run ./tools/codegen_content_service --metadata-dir contracts/metadata --output-dir services/content-service/internal --aggregate Post

codegen-circle-service:
	go run ./tools/codegen_circle_domain --metadata-dir contracts/metadata --output-dir services/circle-service/internal

codegen-rec-model-python:
	go run ./tools/codegen_rec_model_python --metadata-dir contracts/metadata --service-dir recommendation/rec_model --output-dir services/rec-model-service/generated

codegen-storage:
	@echo "=== codegen-storage: user-service ==="
	go run ./tools/codegen_storage --metadata-dir contracts/metadata --manifest services/user-service/codegen_storage_manifest.yaml

# ─── Dev Environment ─────────────────────────────────────────────────
dev:
	docker compose up -d
	@echo "Waiting for services..."
	@sleep 5
	@docker compose ps

dev-down:
	docker compose down -v

dev-redis:
	docker compose -f docker-compose.local-redis.yml up -d
	@docker compose -f docker-compose.local-redis.yml ps

dev-redis-down:
	docker compose -f docker-compose.local-redis.yml down

dev-reliable-task-local: dev-redis

dev-reliable-task-local-down: dev-redis-down

# ─── Clean ───────────────────────────────────────────────────────────
clean:
	go clean -testcache
	rm -rf tmp/

# ─── ML Verification ────────────────────────────────────────────────
verify-ml-features:
	$(ML_PYTHON) scripts/ml/verify_feature_consistency.py

verify-ml-tests:
	$(ML_PYTHON) -m pytest services/rec-model-service/tests -q

verify-ml-model-quality:
	$(ML_PYTHON) scripts/ml/evaluate_gate.py --scenario "$(SCENARIO)" $(if $(filter 1 true yes,$(ML_DRY_RUN)),--dry-run,) --out "eval_report_$(SCENARIO).json"
	$(ML_PYTHON) scripts/ml/evaluate_gate.py --scenario "$(SCENARIO)_multiobjective" $(if $(filter 1 true yes,$(ML_DRY_RUN)),--dry-run,) --out "eval_report_$(SCENARIO)_multiobjective.json"

verify-ml-e2e:
	$(ML_PYTHON) scripts/ml/e2e_learning_loop_verify.py --scenario "$(SCENARIO)" --full-pipeline $(if $(strip $(REC_MODEL_URL)),--rec-model $(REC_MODEL_URL),--skip-service)

verify-ml-e2e-live:
	@test -n "$(strip $(REC_MODEL_URL))" || (echo "REC_MODEL_URL is required for verify-ml-e2e-live" >&2; exit 1)
	$(ML_PYTHON) scripts/ml/e2e_learning_loop_verify.py --scenario "$(SCENARIO)" --mongodb-uri "$(MONGODB_URI)" --db "$(DB)" --rec-model "$(REC_MODEL_URL)"

verify-ml-guardrail:
	$(ML_PYTHON) scripts/ml/online_guardrail.py --scenario "$(SCENARIO)" --window-hours "$(ML_GUARDRAIL_WINDOW_HOURS)" --env "$(ML_GUARDRAIL_ENV)" $(if $(filter 1 true yes,$(ML_GUARDRAIL_DRY_RUN)),--dry-run,) $(if $(strip $(ML_GUARDRAIL_OUT)),--out "$(ML_GUARDRAIL_OUT)",)

verify-ml-drift:
	$(ML_PYTHON) scripts/ml/feature_drift_monitor.py --scenario "$(SCENARIO)" --baseline-date "$(ML_DRIFT_BASELINE_DATE)" $(if $(strip $(ML_DRIFT_OUT)),--out "$(ML_DRIFT_OUT)",)
