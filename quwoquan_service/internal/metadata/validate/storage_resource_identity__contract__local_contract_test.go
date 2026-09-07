package validate

import (
	"os"
	"path/filepath"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestStorageResourceIdentityValidatorAcceptsRepositoryResources(t *testing.T) {
	t.Parallel()

	issues, err := storageResourceIdentityIssues(repositoryMetadataRoot(t))
	if err != nil {
		t.Fatal(err)
	}
	if len(issues) != 0 {
		t.Fatalf("repository storage resource identities are invalid: %+v", issues)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestStorageResourceIdentityValidatorRejectsDerivedCollision(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	paths := []string{
		filepath.Join(metadataDir, "search", "search", "first", "storage.yaml"),
		filepath.Join(metadataDir, "search", "search", "second", "storage.yaml"),
	}
	for _, path := range paths {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte("backend: mongodb\nrole: runtime\nresources:\n  checkpoint:\n    engine: mongodb\n    role: runtime\n"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	issues, err := storageResourceIdentityIssuesWithSource(metadataDir, func(string) (string, error) {
		return "search/search/shared/storage.yaml", nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if !storageResourceIssueCodePresent(issues, "CONTRACT.STORAGE.RESOURCE_IDENTITY_COLLISION") {
		t.Fatalf("expected derived identity collision, got %+v", issues)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestStorageResourceIdentityValidatorRejectsInvalidLocalName(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	path := filepath.Join(metadataDir, "search", "search", "search_index_view", "storage.yaml")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("backend: elasticsearch\nrole: projection\nresources:\n  ProjectionCheckpoints:\n    engine: mongodb\n    role: runtime\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	issues, err := storageResourceIdentityIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if !storageResourceIssueCodePresent(issues, "CONTRACT.STORAGE.RESOURCE_IDENTITY_INVALID") {
		t.Fatalf("expected invalid derived resource identity, got %+v", issues)
	}
}

func repositoryMetadataRoot(t *testing.T) string {
	t.Helper()
	return filepath.Clean(filepath.Join(repositorySchemaRoot(t), ".."))
}

func storageResourceIssueCodePresent(issues []Issue, code string) bool {
	for _, candidate := range issues {
		if candidate.Code == code {
			return true
		}
	}
	return false
}
