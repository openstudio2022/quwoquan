package local_contract

import (
	"testing"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
)

func TestCanonicalEntityIDInfersSemanticSlug(t *testing.T) {
	if got, want := homepagemodel.CanonicalEntityID("sight", "west_lake"), "entity:sight:west_lake"; got != want {
		t.Fatalf("CanonicalEntityID = %q, want %q", got, want)
	}
	if got := homepagemodel.CanonicalEntityID("", "unknown"); got != "" {
		t.Fatalf("CanonicalEntityID should stay empty without a type, got %q", got)
	}
}

func TestCanonicalEntityIDPreservesCanonicalLookupIdentity(t *testing.T) {
	canonical := homepagemodel.CanonicalEntityID("sight", "west_lake")
	if got := homepagemodel.StableID(canonical, "", "", "sight", "ignored title"); got == "" {
		t.Fatal("canonical identity must produce a stable homepage identifier")
	}
}
