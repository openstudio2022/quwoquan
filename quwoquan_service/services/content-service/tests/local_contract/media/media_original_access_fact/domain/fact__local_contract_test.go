package domain_test

import (
	"errors"
	"testing"
	"time"

	originalaccessmodel "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/model"
)

func TestFactEnforcesImmutableDecisionLifecycle(t *testing.T) {
	now := time.Date(2030, time.March, 4, 5, 6, 7, 0, time.UTC)
	valid := originalaccessmodel.Fact{
		AuditID: "moa_fact", AssetID: "media_1", ViewerID: "persona_1",
		Purpose: "save", Outcome: "granted", Reason: "authorized",
		IdempotencyKey: "original-access-1", GrantedAt: now,
		ExpiresAt: now.Add(5 * time.Minute),
	}
	if err := valid.Validate(); err != nil {
		t.Fatalf("valid immutable fact rejected: %v", err)
	}
	invalid := valid
	invalid.ExpiresAt = time.Time{}
	if !errors.Is(invalid.Validate(), originalaccessmodel.ErrInvalidMediaOriginalAccessFact) {
		t.Fatal("granted fact without absolute expiry must be rejected")
	}
	invalid = valid
	invalid.Outcome = "denied"
	invalid.Reason = "authorized"
	if !errors.Is(invalid.Validate(), originalaccessmodel.ErrInvalidMediaOriginalAccessFact) {
		t.Fatal("denied fact with grant reason must be rejected")
	}
}
