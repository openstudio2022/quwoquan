.PHONY: build test test-contract test-unit gate dev clean

# --- Build ---
build:
	go build -o bin/circle-service ./cmd/api

# --- Test ---
test: test-contract

test-contract:
	cd tests && go test -v -count=1 -timeout 120s ./...

test-contract-local:
	cd tests && go test -v -count=1 -timeout 120s -run "TestCreate|TestGet|TestList" ./...

test-unit:
	go test -v -count=1 ./internal/...

# --- Gate ---
gate: build test

# --- Dev ---
dev:
	APP_ENV=local go run ./cmd/api

# --- Clean ---
clean:
	rm -rf bin/
