// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
package local_contract

import (
	"testing"

	releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"
)

func TestCreatorPersonaCommandMetaSeparatesActivationRuns(t *testing.T) {
	state := releaseimport.CreatorPersonaState{
		ReleaseID:   "release-a",
		UserID:      "creator-user-a",
		PersonaID:   "creator-persona-a",
		DisplayName: "Creator A",
	}

	first, err := releaseimport.CreatorPersonaCommandMeta(state, "candidate-import-1")
	if err != nil {
		t.Fatalf("first command meta: %v", err)
	}
	firstRetry, err := releaseimport.CreatorPersonaCommandMeta(state, "candidate-import-1")
	if err != nil {
		t.Fatalf("retry command meta: %v", err)
	}
	replay, err := releaseimport.CreatorPersonaCommandMeta(state, "candidate-import-2")
	if err != nil {
		t.Fatalf("replay command meta: %v", err)
	}

	if first.IdempotencyKey != firstRetry.IdempotencyKey {
		t.Fatalf("same import run must retain one idempotency key")
	}
	if first.IdempotencyKey == replay.IdempotencyKey {
		t.Fatalf("different activation runs must not reuse stale command receipts")
	}
	if first.CommandDigest != replay.CommandDigest {
		t.Fatalf("activation identity must not change the immutable Persona payload digest")
	}
}

func TestCreatorPersonaCommandMetaRequiresImportRunID(t *testing.T) {
	_, err := releaseimport.CreatorPersonaCommandMeta(
		releaseimport.CreatorPersonaState{
			ReleaseID: "release-a",
			PersonaID: "creator-persona-a",
		},
		" ",
	)
	if err == nil {
		t.Fatalf("empty import run ID must fail closed")
	}
}
