.PHONY: build test test-contract gate lint clean

build:
	go build ./...

test:
	go test ./... -v -count=1

test-contract:
	go test ./tests/ -v -count=1 -run Contract

gate: build test

lint:
	golangci-lint run ./...

clean:
	go clean -testcache
