package load_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestBusinessObjectMapRejectsObjectKindAsFieldRole(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeBusinessObjectMapFixture(t, metadataDir, "context.yaml", `
role: core
access:
  commands: aggregate_facade_only
  queries: named_reader_slice_only
  child_objects: aggregate_root_only
  cross_context: public_contract_only
`)
	writeBusinessObjectMapFixture(t, metadataDir, "post/object.yaml", `
kind: aggregate_root
identity:
  fields: [id]
  version_source: store_commit
access:
  commands: aggregate_facade
  queries: named_reader
  cross_context: public_contract_only
relationships: []
`)
	writeBusinessObjectMapFixture(t, metadataDir, "post/fields.yaml", `
fields:
  - name: id
    type: string
    role: owned_entity
`)

	_, err := load.Load(metadataDir)
	if err == nil {
		t.Fatal("object/member kind owned_entity was accepted as a field role")
	}
	if !strings.Contains(err.Error(), `fields[0].role "owned_entity" is not canonical`) {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestContractGraphSchemaRejectsNonCanonicalFieldRoleKey(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	writeBusinessObjectMapFixture(t, metadataDir, "context.yaml", `
role: core
access:
  commands: aggregate_facade_only
  queries: named_reader_slice_only
  child_objects: aggregate_root_only
  cross_context: public_contract_only
`)
	writeBusinessObjectMapFixture(t, metadataDir, "post/object.yaml", `
kind: aggregate_root
identity:
  fields: [id]
  version_source: store_commit
access:
  commands: aggregate_facade
  queries: named_reader
  cross_context: public_contract_only
relationships: []
`)
	writeBusinessObjectMapFixture(t, metadataDir, "post/fields.yaml", `
fields:
  - name: id
    type: string
    role: authoritative_state
`)
	copyBusinessObjectMapSchema(t, metadataDir)

	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load valid fixture: %v", err)
	}
	contractGraph := graph.Build(catalog)
	if err := validate.ContractGraphSchema(metadataDir, contractGraph); err != nil {
		t.Fatalf("validate canonical field roles: %v", err)
	}
	contractGraph.BusinessObjectMaps[0].Objects[0].FieldRoles["owned_entity"] = []string{"id"}
	if err := validate.ContractGraphSchema(metadataDir, contractGraph); err == nil {
		t.Fatal("ContractGraph schema accepted owned_entity as a fieldRoles key")
	}
}

func TestFilterCatalogReleaseDerivesCanonicalAccessAndOwnedDeletePolicy(t *testing.T) {
	t.Parallel()

	metadataDir := contractsview.Build(t)
	catalog, err := load.Load(metadataDir)
	if err != nil {
		t.Fatalf("load service contract view: %v", err)
	}
	contractGraph := graph.Build(catalog)
	if err := validate.ContractGraphSchema(metadataDir, contractGraph); err != nil {
		t.Fatalf("validate derived ContractGraph schema: %v", err)
	}
	for _, objectMap := range contractGraph.BusinessObjectMaps {
		for _, object := range objectMap.Objects {
			if object.CanonicalObject != "FilterCatalogRelease" {
				continue
			}
			if object.Access.CrossContext != "public_contract_only" {
				t.Fatalf("FilterCatalogRelease cross-context access = %q", object.Access.CrossContext)
			}
			if len(object.Relationships) != 3 {
				t.Fatalf("FilterCatalogRelease relationships = %d, want 3", len(object.Relationships))
			}
			for _, relationship := range object.Relationships {
				if relationship.OnDelete != "cascade" {
					t.Fatalf("FilterCatalogRelease.%s onDelete = %q", relationship.Name, relationship.OnDelete)
				}
			}
			return
		}
	}
	t.Fatal("FilterCatalogRelease missing from derived business object map")
}

func writeBusinessObjectMapFixture(t *testing.T, metadataDir, relativePath, content string) {
	t.Helper()
	path := filepath.Join(metadataDir, "content", "content", relativePath)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("create fixture directory: %v", err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write fixture %s: %v", relativePath, err)
	}
}

func copyBusinessObjectMapSchema(t *testing.T, metadataDir string) {
	t.Helper()
	source := filepath.Join("..", "..", "..", "contracts", "metadata", "_schemas", "contract_graph.schema.json")
	data, err := os.ReadFile(source)
	if err != nil {
		t.Fatalf("read ContractGraph schema: %v", err)
	}
	target := filepath.Join(metadataDir, "_schemas", "contract_graph.schema.json")
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatalf("create schema fixture directory: %v", err)
	}
	if err := os.WriteFile(target, data, 0o644); err != nil {
		t.Fatalf("write ContractGraph schema fixture: %v", err)
	}
}
