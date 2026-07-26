package local_contract

import (
	"testing"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

// TestMigratedRelationshipStoreUsesCanonicalPair verifies the public relationship aggregate identity contract.
func TestMigratedRelationshipStoreUsesCanonicalPair(t *testing.T) {
	pair, err := relmodel.NewPair("persona-b", "persona-a")
	if err != nil {
		t.Fatalf("NewPair() error = %v", err)
	}
	if pair.LowerPersonaID != "persona-a" || pair.UpperPersonaID != "persona-b" || pair.ID == "" {
		t.Fatalf("canonical pair = %#v", pair)
	}
}
