.PHONY: gate build test test-unit test-integration lint verify-metadata codegen-app codegen-content-service dev dev-down clean

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
	go test ./runtime/... -v -count=1

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
