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

func TestFieldTypeToGoTypeAcceptsCanonicalStringSlice(t *testing.T) {
	t.Parallel()

	if got := fieldTypeToGoType(nil, "Persona", "OverriddenProfileFields", "[]string", false); got != "[]string" {
		t.Fatalf("canonical []string mapped to %q, want []string", got)
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

func TestPGStoreRejectsEntitylessBusinessTable(t *testing.T) {
	t.Parallel()

	ctx := &genContext{
		manifest: &Manifest{OutputDir: t.TempDir()},
		source: Source{
			DomainPkg: "user",
		},
	}
	err := generatePGStore(ctx, "greeting_request_outbox", TableDef{})
	if err == nil {
		t.Fatal("entityless table must not generate pg__store.g.go")
	}
}

func TestModelGenerationRejectsEntitylessBusinessTableBeforeWriting(t *testing.T) {
	t.Parallel()

	outputDir := t.TempDir()
	ctx := &genContext{
		manifest: &Manifest{OutputDir: outputDir},
		source: Source{
			DomainPkg: "user",
		},
		storage: &StorageYAML{
			Backend: "postgresql",
			Tables: map[string]TableDef{
				"greeting_request_outbox": {},
			},
		},
		fields: &FieldsYAML{},
	}
	if err := generateModels(ctx); err == nil {
		t.Fatal("entityless table must fail before model generation")
	}
	if _, err := os.Stat(filepath.Join(outputDir, "domain/user/model/.g.go")); !os.IsNotExist(err) {
		t.Fatalf("empty-name model must not be written, stat err=%v", err)
	}
}
