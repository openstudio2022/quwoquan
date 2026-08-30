// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
	ownerinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
)

func TestCheckedInGeneratedRegistryEntriesUseRealRuntimeBindings(t *testing.T) {
	path := filepath.Join(
		graphqlRegistryServiceRoot(t),
		"services/api-edge/resources/policies/graphql_read/persisted_query_registry.example.json",
	)
	encoded, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var generated struct {
		Entries []domain.Entry `json:"entries"`
	}
	if err := json.Unmarshal(encoded, &generated); err != nil {
		t.Fatalf("decode checked-in generated registry: %v", err)
	}
	registry, err := domain.NewRegistry(generated.Entries)
	if err != nil {
		t.Fatalf("load checked-in generated registry through runtime domain: %v", err)
	}
	entries := registry.Entries()
	for _, entry := range entries {
		if err := ownerinfra.ValidateExecutableEntry(entry); err != nil {
			t.Fatalf("generated operation %s has no exact runtime binding: %v", entry.OperationName, err)
		}
	}
}

func graphqlRegistryServiceRoot(t *testing.T) string {
	t.Helper()
	directory, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(directory, "go.mod")); err == nil {
			return directory
		}
		parent := filepath.Dir(directory)
		if parent == directory {
			t.Fatal("quwoquan_service module root not found")
		}
		directory = parent
	}
}
