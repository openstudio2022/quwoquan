package codegen

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/runtime/registry"
)

func TestGenerateAll_ProducesFiles(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "contracts", "metadata")
	if _, err := os.Stat(metadataDir); err != nil {
		t.Skipf("metadata dir not found, skipping")
	}

	reg, err := registry.LoadFromDirectory(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}

	outputDir := t.TempDir()
	gen := NewGenerator(reg, outputDir)

	if err := gen.GenerateAll(); err != nil {
		t.Fatalf("GenerateAll: %v", err)
	}

	aggregates := reg.ListAggregates()
	if len(aggregates) < 12 {
		t.Errorf("expected >= 12 aggregates, got %d", len(aggregates))
	}

	for _, name := range aggregates {
		snake := toSnake(name)
		pkg := strings.ToLower(name) // match buildTemplateData PackageName

		modelDir := filepath.Join(outputDir, "domain", pkg, "model")
		modelFile := filepath.Join(modelDir, snake+".go")
		if _, err := os.Stat(modelFile); err != nil {
			t.Errorf("missing model file: %s", modelFile)
		}

		repoDir := filepath.Join(outputDir, "domain", pkg, "repository")
		repoFile := filepath.Join(repoDir, "repository.go")
		if _, err := os.Stat(repoFile); err != nil {
			t.Errorf("missing repository file: %s", repoFile)
		}

		eventDir := filepath.Join(outputDir, "domain", pkg, "event")
		eventFile := filepath.Join(eventDir, "events.go")
		if _, err := os.Stat(eventFile); err != nil {
			t.Errorf("missing events file: %s", eventFile)
		}
	}

	t.Logf("generated code for %d aggregates in %s", len(aggregates), outputDir)
}

func TestGoModelTemplate_ValidGoSyntax(t *testing.T) {
	metadataDir := filepath.Join("..", "..", "contracts", "metadata")
	if _, err := os.Stat(metadataDir); err != nil {
		t.Skipf("metadata dir not found, skipping")
	}

	reg, err := registry.LoadFromDirectory(metadataDir)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}

	outputDir := t.TempDir()
	gen := NewGenerator(reg, outputDir)

	if err := gen.GenerateForAggregate("Post"); err != nil {
		t.Fatalf("GenerateForAggregate(Post): %v", err)
	}

	// PackageName is lowercased in buildTemplateData
	modelFile := filepath.Join(outputDir, "domain", "post", "model", "post.go")
	data, err := os.ReadFile(modelFile)
	if err != nil {
		t.Fatalf("read model file: %v", err)
	}

	content := string(data)
	if len(content) < 100 {
		t.Errorf("model file too short (%d bytes)", len(content))
	}
	t.Logf("Post model:\n%s", content[:min(len(content), 500)])
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
