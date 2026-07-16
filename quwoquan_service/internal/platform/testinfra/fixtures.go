package testinfra

import (
	"encoding/json"
	"os"
	"testing"
)

func LoadJSONFixture[T any](t *testing.T, path string) T {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("testinfra: read fixture %s: %v", path, err)
	}
	var out T
	if err := json.Unmarshal(data, &out); err != nil {
		t.Fatalf("testinfra: decode fixture %s: %v", path, err)
	}
	return out
}

func RoundTripJSON[T any](t *testing.T, in T) T {
	t.Helper()
	data, err := json.Marshal(in)
	if err != nil {
		t.Fatalf("testinfra: marshal fixture: %v", err)
	}
	var out T
	if err := json.Unmarshal(data, &out); err != nil {
		t.Fatalf("testinfra: unmarshal fixture: %v", err)
	}
	return out
}
