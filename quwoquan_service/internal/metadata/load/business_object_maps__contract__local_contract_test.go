package load_test

import (
	"testing"

	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
)

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
