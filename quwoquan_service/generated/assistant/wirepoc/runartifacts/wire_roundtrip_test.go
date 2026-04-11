package runartifacts

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestRunArtifactsWireJSONRoundTrip(t *testing.T) {
	t.Parallel()
	root := findServiceRoot(t)
	p := filepath.Join(root, "contracts", "metadata", "assistant", "test_fixtures", "wire_min_run_artifacts.json")
	raw, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var v RunArtifacts
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	out, err := json.Marshal(&v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var v2 RunArtifacts
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
