.PHONY: build test gate clean

build:
	go build ./...

test:
	go test ./... -v -count=1

gate: build test

clean:
	go clean -testcache
