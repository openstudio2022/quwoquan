// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
package local_contract

import (
	"encoding/json"
	"testing"
	"time"

	usermodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
)

func TestGreetingIntersectionReferenceContainsIntentOnly(t *testing.T) {
	t.Parallel()
	ref := usermodel.GreetingIntersectionRef{
		IntersectionID: " intersection-1 ",
		EvidenceID:     " evidence-1 ",
		SourceRef:      " coVisitedEntity ",
		ObjectTypeRef:  " user ",
		ObjectID:       " persona-b ",
	}
	payload := usermodel.EncodeIntersectionRef(&ref)
	if len(payload) == 0 {
		t.Fatal("complete greeting intersection reference must be encoded")
	}
	var wire map[string]any
	if err := json.Unmarshal(payload, &wire); err != nil {
		t.Fatalf("decode greeting intersection reference: %v", err)
	}
	if wire["objectId"] != "persona-b" || wire["sourceRef"] != "coVisitedEntity" {
		t.Fatalf("reference was not normalized: %#v", wire)
	}
	if _, leaked := wire["primaryText"]; leaked {
		t.Fatalf("client intent reference must not carry display text: %#v", wire)
	}
}

func TestGreetingIntersectionSnapshotRoundTrip(t *testing.T) {
	t.Parallel()
	resolvedAt := time.Date(2026, time.July, 31, 8, 0, 0, 0, time.UTC)
	want := &usermodel.GreetingIntersectionSnapshot{
		IntersectionID: "intersection-1",
		EvidenceID:     "evidence-1",
		SourceRef:      "coVisitedEntity",
		ObjectTypeRef:  "user",
		ObjectID:       "persona-b",
		PrimaryText:    "你们都去过老君山",
		Dimension:      "destination",
		ResolvedAt:     resolvedAt,
	}
	got := usermodel.DecodeIntersectionSnapshot(
		usermodel.EncodeIntersectionSnapshot(want),
	)
	if got == nil || got.PrimaryText != want.PrimaryText ||
		!got.ResolvedAt.Equal(resolvedAt) {
		t.Fatalf("snapshot round trip mismatch: got=%+v want=%+v", got, want)
	}
}
