package local_contract

import (
	"testing"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

func TestPersonaRelationshipPairCanonicalIdentity(t *testing.T) {
	forward, err := relmodel.NewPair("persona-a", "persona-b")
	if err != nil {
		t.Fatalf("NewPair forward: %v", err)
	}
	reverse, err := relmodel.NewPair("persona-b", "persona-a")
	if err != nil {
		t.Fatalf("NewPair reverse: %v", err)
	}
	if forward.ID == "" || forward.ID != reverse.ID {
		t.Fatalf("pair identity must be non-empty and order-independent: forward=%+v reverse=%+v", forward, reverse)
	}
	if forward.LowerPersonaID != "persona-a" || forward.UpperPersonaID != "persona-b" {
		t.Fatalf("pair ordering=%+v, want persona-a/persona-b", forward)
	}
}

func TestPersonaRelationshipPairRejectsInvalidParticipants(t *testing.T) {
	for _, pair := range [][2]string{{"", "persona-b"}, {"persona-a", ""}, {"persona-a", "persona-a"}} {
		if _, err := relmodel.NewPair(pair[0], pair[1]); err != relmodel.ErrInvalidPersonaPair {
			t.Fatalf("NewPair(%q, %q) error=%v, want ErrInvalidPersonaPair", pair[0], pair[1], err)
		}
	}
}
