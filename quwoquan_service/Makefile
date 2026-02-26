.PHONY: gate build test test-unit test-contract test-integration lint verify-metadata codegen-app codegen-content-service codegen-rec-model-python dev dev-down clean

# ─── Quality Gate ────────────────────────────────────────────────────
gate:
	@bash scripts/gate.sh

# ─── Build ───────────────────────────────────────────────────────────
build:
	go build ./runtime/...
	go build ./tools/...

# ─── Test ────────────────────────────────────────────────────────────
test: test-unit

test-unit:
	go test ./runtime/... ./services/content-service/... -v -count=1

test-contract:
	go test ./services/content-service/... -v -count=1

test-integration:
	go test ./runtime/... -v -count=1 -tags=integration

# ─── Lint ────────────────────────────────────────────────────────────
lint:
	go vet ./runtime/...
	go vet ./tools/...

# ─── Metadata ────────────────────────────────────────────────────────
verify-metadata:
	go run ./tools/verify_metadata/ contracts/metadata

codegen-app:
	go run ./tools/codegen_app_metadata --metadata-dir contracts/metadata --app-dir ../quwoquan_app

codegen-content-service:
	go run ./tools/codegen_content_service --metadata-dir contracts/metadata --output-dir services/content-service/internal --aggregate Post

codegen-rec-model-python:
	go run ./tools/codegen_rec_model_python --metadata-dir contracts/metadata --output-dir services/rec-model-service/generated

# ─── Dev Environment ─────────────────────────────────────────────────
dev:
	docker compose up -d
	@echo "Waiting for services..."
	@sleep 5
	@docker compose ps

dev-down:
	docker compose down -v

# ─── Clean ───────────────────────────────────────────────────────────
clean:
	go clean -testcache
	rm -rf tmp/
