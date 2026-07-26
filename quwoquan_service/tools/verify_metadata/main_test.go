package main

import (
	"path/filepath"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func TestRepositoryMetadataUsesObjectFirstSingleTrack(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "contracts", "metadata")
	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		t.Fatalf("compile metadata: %v", err)
	}
	v := &validator{metadataDir: metadataDir, source: source}
	v.run()
	if len(v.errors) != 0 {
		t.Fatalf("metadata validation errors: %v", v.errors)
	}

	objects, err := filepath.Glob(filepath.Join(metadataDir, "*", "*", "*", "object.yaml"))
	if err != nil {
		t.Fatalf("scan object metadata: %v", err)
	}
	if len(objects) != 85 {
		t.Fatalf("independent object roots = %d, want 85", len(objects))
	}
	for _, pattern := range []string{
		filepath.Join(metadataDir, "*", "business_object_map.yaml"),
		filepath.Join(metadataDir, "*", "*", "*", "readiness.yaml"),
		filepath.Join(metadataDir, "*", "*", "*", "aggregate.yaml"),
		filepath.Join(metadataDir, "*", "*", "*", "entity.yaml"),
	} {
		matches, globErr := filepath.Glob(pattern)
		if globErr != nil {
			t.Fatalf("scan forbidden metadata: %v", globErr)
		}
		if len(matches) != 0 {
			t.Fatalf("forbidden metadata remains: %v", matches)
		}
	}
}
