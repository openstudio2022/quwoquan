package validate

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestStorageRedisSceneValidationDoesNotRequireSharedContractForUnrelatedFixture(t *testing.T) {
	t.Parallel()

	issues, err := storageRedisSceneIssues(t.TempDir())
	if err != nil {
		t.Fatalf("unrelated partial fixture requires Redis keyspace: %v", err)
	}
	if len(issues) != 0 {
		t.Fatalf("issues = %+v, want none", issues)
	}
}

func TestStorageRedisSceneValidationRequiresSharedContractForExplicitScene(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeStorageSceneFixture(t, metadataDir, "rec:session:{actor}", "rec")
	_, err := storageRedisSceneIssues(metadataDir)
	if err == nil || !strings.Contains(err.Error(), "read Redis keyspace") {
		t.Fatalf("error = %v, want missing shared Redis keyspace", err)
	}
}

func TestStorageRedisSceneValidationRejectsRouteMismatch(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeStorageSceneFixture(t, metadataDir, "rec:session:{actor}", "general")
	sharedDir := filepath.Join(metadataDir, "_shared")
	if err := os.MkdirAll(sharedDir, 0o755); err != nil {
		t.Fatal(err)
	}
	keyspace := `scene_routing:
  fallback: general
  scenes:
    general:
      key_prefixes: ["cache:"]
    rec:
      key_prefixes: ["rec:"]
`
	if err := os.WriteFile(filepath.Join(sharedDir, "redis_keyspace.yaml"), []byte(keyspace), 0o600); err != nil {
		t.Fatal(err)
	}

	issues, err := storageRedisSceneIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if len(issues) != 1 || issues[0].Code != "CONTRACT.STORAGE.REDIS_SCENE_MISMATCH" {
		t.Fatalf("issues = %+v, want one route mismatch", issues)
	}
}

func writeStorageSceneFixture(t *testing.T, metadataDir, key, scene string) {
	t.Helper()
	objectDir := filepath.Join(metadataDir, "recommendation", "recommendation", "feed")
	if err := os.MkdirAll(objectDir, 0o755); err != nil {
		t.Fatal(err)
	}
	document := "backend: redis\nrole: projection\nredis_cache:\n  - key: " + key + "\n    scene: " + scene + "\n    type: string\n    ttl_seconds: 60\n"
	if err := os.WriteFile(filepath.Join(objectDir, "storage.yaml"), []byte(document), 0o600); err != nil {
		t.Fatal(err)
	}
}
