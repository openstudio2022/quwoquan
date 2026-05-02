package runtimefailure

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestRuntimeFailureWireWireJSONRoundTrip(t *testing.T) {
	t.Parallel()
	root := findServiceRoot(t)
	p := filepath.Join(root, "contracts", "metadata", "assistant", "test_fixtures", "m2_runtime_failure_min.json")
	raw, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var v RuntimeFailureWire
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	out, err := json.Marshal(&v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var v2 RuntimeFailureWire
	if err := json.Unmarshal(out, &v2); err != nil {
		t.Fatalf("roundtrip unmarshal: %v", err)
	}
}

func findServiceRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for d := dir; d != "/" && d != "."; d = filepath.Dir(d) {
		if _, err := os.Stat(filepath.Join(d, "go.mod")); err == nil {
			return d
		}
	}
	t.Fatal("go.mod not found from cwd")
	return ""
}
