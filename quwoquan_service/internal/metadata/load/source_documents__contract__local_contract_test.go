package load

import (
	"os"
	"path/filepath"
	"testing"
)

func TestFixturePayloadIsDigestedButNotEmbedded(t *testing.T) {
	root := t.TempDir()
	fixturePath := filepath.Join(
		root,
		"content",
		"test_fixtures",
		"large_seed.json",
	)
	if err := os.MkdirAll(filepath.Dir(fixturePath), 0o755); err != nil {
		t.Fatalf("mkdir fixture: %v", err)
	}
	if err := os.WriteFile(
		fixturePath,
		[]byte(`{"items":[{"id":"seed-1"}]}`),
		0o644,
	); err != nil {
		t.Fatalf("write fixture: %v", err)
	}

	catalog, err := Load(root)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	if len(catalog.Sources) != 1 {
		t.Fatalf("sources=%d, want 1", len(catalog.Sources))
	}
	if len(catalog.Documents) != 0 {
		t.Fatalf("documents=%d, fixture payload must not be embedded", len(catalog.Documents))
	}
}
