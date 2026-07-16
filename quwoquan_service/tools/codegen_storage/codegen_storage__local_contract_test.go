package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestSourceRoutesGeneratedOwnershipToObjectPacket(t *testing.T) {
	t.Parallel()

	source := Source{
		DomainPkg:  "profile_update_proposal",
		DomainPath: "persona/profile_update_proposal",
	}
	if got, want := source.modelImport("example/internal"), "example/internal/domain/persona/profile_update_proposal/model"; got != want {
		t.Fatalf("model import = %q, want %q", got, want)
	}
	if got, want := filepath.ToSlash(source.infrastructurePath("persistence")), "infrastructure/persona/profile_update_proposal/persistence"; got != want {
		t.Fatalf("persistence path = %q, want %q", got, want)
	}
}

func TestManifestRejectsDomainPathTraversal(t *testing.T) {
	t.Parallel()

	path := filepath.Join(t.TempDir(), "manifest.yaml")
	if err := os.WriteFile(path, []byte(`
service: user-service
output_dir: services/user-service/internal
module_path: example/internal
sources:
  - metadata: user/profile_update_proposal
    domain_pkg: profile_update_proposal
    domain_path: ../../outside
`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := loadManifest(path); err == nil {
		t.Fatal("domain_path traversal must be rejected")
	}
}
