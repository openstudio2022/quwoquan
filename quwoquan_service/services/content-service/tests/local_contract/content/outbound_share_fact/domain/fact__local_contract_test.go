// spec_ref: specs/feature-tree/product-ops-growth/outbound-share-distribution/share-attribution-and-token/spec.md#gwt-001
// readiness_case: append-outbound-share-fact-local
package domain_test

import (
	"testing"
	"time"

	sharemodel "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/model"
)

func TestOutboundShareFactRequiresCompleteImmutableIdentityAndLifecycleData(t *testing.T) {
	valid := sharemodel.Fact{
		EventID:           "osf-contract",
		PostID:            "post-contract",
		ActorDimension:    sharemodel.ActorDimensionPersona,
		ActorID:           "persona-contract",
		Channel:           sharemodel.ChannelSystemShare,
		DestinationKind:   sharemodel.DestinationKindExternalApp,
		DestinationDigest: "destination-digest",
		ReferralID:        "referral-contract",
		IdempotencyKey:    "idempotency-contract",
		OccurredAt:        time.Date(2026, 8, 2, 8, 0, 0, 0, time.UTC),
	}
	if err := valid.Validate(); err != nil {
		t.Fatalf("valid OutboundShareFact rejected: %v", err)
	}

	invalid := valid
	invalid.EventID = ""
	if err := invalid.Validate(); err == nil {
		t.Fatal("OutboundShareFact without event identity must be rejected")
	}
	invalid = valid
	invalid.ActorDimension = "account"
	if err := invalid.Validate(); err == nil {
		t.Fatal("OutboundShareFact with a non-canonical actor dimension must be rejected")
	}
	invalid = valid
	invalid.Channel = "unsupported_share"
	if err := invalid.Validate(); err == nil {
		t.Fatal("OutboundShareFact with a non-canonical channel must be rejected")
	}
}
