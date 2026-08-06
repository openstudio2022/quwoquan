package load

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestRepositoryPrivacyDocumentsUseTheStrictTypedReader(t *testing.T) {
	t.Parallel()

	paths, err := filepath.Glob(filepath.Join(
		privacyServiceRoot(t), "services", "*", "contracts", "*", "*", "privacy.yaml",
	))
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) != 2 {
		t.Fatalf("privacy corpus = %d documents, want current repository inventory 2", len(paths))
	}
	for _, path := range paths {
		document, loadErr := loadPrivacyDocument(path)
		if loadErr != nil {
			t.Errorf("strict decode %s: %v", path, loadErr)
			continue
		}
		if strings.TrimSpace(document.Description) == "" {
			t.Errorf("strict decode %s lost description", path)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestPrivacyTypedReaderRejectsUnknownNestedKeysAndTrailingDocuments(t *testing.T) {
	t.Parallel()

	for name, source := range map[string]string{
		"unknown app log key": `
description: fixture
app_log_policy:
  - field: phone
    classification: PII
    app_log: drop
    debug_hint: secret
`,
		"retired lifecycle alias": `
description: fixture
data_lifecycle:
  retention_days: 30
  deletion_on_user_request: true
  user_deletion_hook: true
`,
		"retired target identity": `
description: fixture
data_lifecycle:
  retention_days: 30
  deletion_on_user_request: true
  deletion_cascade:
    - entity: Persona
      strategy: hard_delete
`,
		"trailing YAML document": `
description: fixture
field_visibility:
  - field: phone
    visibility: [self]
---
description: second
`,
	} {
		name := name
		source := source
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			if _, err := decodePrivacyDocument([]byte(source)); err == nil {
				t.Fatal("typed privacy reader accepted non-canonical source")
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestPrivacyIdentityComesOnlyFromOwningObjectPath(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	objectDir := filepath.Join(metadataDir, "content", "post")
	if err := os.MkdirAll(objectDir, 0o755); err != nil {
		t.Fatal(err)
	}
	privacyPath := filepath.Join(objectDir, "privacy.yaml")
	if err := os.WriteFile(privacyPath, []byte(`
description: fixture
field_visibility:
  - field: _id
    visibility: [never_expose]
`), 0o600); err != nil {
		t.Fatal(err)
	}
	definition, err := loadPrivacyGovernance(
		metadataDir,
		objectDir,
		ast.Object{ID: "content.post", Domain: "content", Name: "Post"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if definition.ObjectID != "content.post" {
		t.Fatalf("privacy object ID = %q, want path-derived content.post", definition.ObjectID)
	}
	if definition.SourcePath != "content/post/privacy.yaml" {
		t.Fatalf("privacy source path = %q", definition.SourcePath)
	}
}

func privacyServiceRoot(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(thisFile), "..", "..", ".."))
}
