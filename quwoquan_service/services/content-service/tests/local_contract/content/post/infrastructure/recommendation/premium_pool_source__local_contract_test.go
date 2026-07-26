package recommendation_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
)

func TestPremiumPoolProjectionFieldsFailClosed(t *testing.T) {
	now := time.Date(2026, 6, 25, 10, 0, 0, 0, time.UTC)
	fields := BuildPremiumPoolProjectionFields(PremiumPoolProjectionInput{
		ContentID:        "post_premium_1",
		Scope:            "global",
		Status:           "active",
		QualityAdmission: "approved",
		QualityScore:     0.91,
		SupplySource:     "data_engineering",
		AuditID:          "audit_1",
		RollbackToken:    "rbk_1",
		ExpiresAt:        now.Add(24 * time.Hour),
	}, now)

	if got := fields["eligibilityState"]; got != "eligible" {
		t.Fatalf("eligibilityState=%v want eligible", got)
	}
	if got := fields["projectionVersion"]; got != PremiumPoolProjectionVersion {
		t.Fatalf("projectionVersion=%v want %s", got, PremiumPoolProjectionVersion)
	}

	expired := BuildPremiumPoolProjectionFields(PremiumPoolProjectionInput{
		ContentID:        "post_premium_2",
		Scope:            "circle",
		Status:           "active",
		QualityAdmission: "approved",
		QualityScore:     0.91,
		ExpiresAt:        now.Add(-time.Minute),
	}, now)
	if got := expired["eligibilityState"]; got != "ineligible" {
		t.Fatalf("expired eligibilityState=%v want ineligible", got)
	}
	reasons := expired["ineligibleReasons"].([]string)
	if !containsString(reasons, "non_global_scope") || !containsString(reasons, "expired") {
		t.Fatalf("ineligibleReasons=%v must include non_global_scope and expired", reasons)
	}

	rolledBack := BuildPremiumPoolProjectionFields(PremiumPoolProjectionInput{
		ContentID:        "post_premium_3",
		Scope:            "global",
		Status:           "rolled_back",
		QualityAdmission: "approved",
		QualityScore:     0.91,
		ExpiresAt:        now.Add(time.Hour),
	}, now)
	if got := rolledBack["eligibilityState"]; got != "ineligible" {
		t.Fatalf("rolledBack eligibilityState=%v want ineligible", got)
	}
}

func TestPremiumPoolSourceGatesToPremiumStream(t *testing.T) {
	reader := &stubPremiumPoolReader{
		items: []rtrec.ContentCandidate{{
			ContentID:    "post_premium_1",
			QualityScore: 0.91,
			SupplySource: "data_engineering",
			RecallPath:   "old_path",
		}},
	}
	src := NewPremiumPoolSource(reader)
	src.SetNow(func() time.Time { return time.Date(2026, 6, 25, 10, 0, 0, 0, time.UTC) })

	home, err := src.Recall(context.Background(), rtrec.RecallRequest{
		FeedType: rtrec.FeedDiscovery,
		Surface:  "home",
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("home recall err=%v", err)
	}
	if len(home) != 0 || reader.calls != 0 {
		t.Fatalf("home recall must be gated off, items=%d calls=%d", len(home), reader.calls)
	}

	premium, err := src.Recall(context.Background(), rtrec.RecallRequest{
		FeedType: rtrec.FeedSimilar,
		Surface:  "premium_stream",
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("premium recall err=%v", err)
	}
	if reader.calls != 1 {
		t.Fatalf("reader calls=%d want 1", reader.calls)
	}
	if len(premium) != 1 {
		t.Fatalf("premium items=%d want 1", len(premium))
	}
	if premium[0].RecallPath != PremiumPoolRecallPath {
		t.Fatalf("RecallPath=%s want %s", premium[0].RecallPath, PremiumPoolRecallPath)
	}
}

func TestGatePremiumStreamSourceBlocksGenericSource(t *testing.T) {
	generic := &stubCandidateSource{
		items: []rtrec.ContentCandidate{{ContentID: "generic_1"}},
	}
	gated := GatePremiumStreamSource(generic)

	premium, err := gated.Recall(context.Background(), rtrec.RecallRequest{
		FeedType: rtrec.FeedSimilar,
		Surface:  "premium_stream",
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("premium recall err=%v", err)
	}
	if len(premium) != 0 || generic.calls != 0 {
		t.Fatalf("generic source must be blocked for premium_stream, items=%d calls=%d", len(premium), generic.calls)
	}

	home, err := gated.Recall(context.Background(), rtrec.RecallRequest{
		FeedType: rtrec.FeedDiscovery,
		Surface:  "home",
		Limit:    10,
	})
	if err != nil {
		t.Fatalf("home recall err=%v", err)
	}
	if len(home) != 1 || generic.calls != 1 {
		t.Fatalf("generic source must stay active for home, items=%d calls=%d", len(home), generic.calls)
	}
}

func TestPremiumPoolProjectionFailsClosedOnRejectedAdmission(t *testing.T) {
	fields := BuildPremiumPoolProjectionFields(PremiumPoolProjectionInput{
		ContentID:        "post_4",
		Scope:            "global",
		Status:           "active",
		QualityAdmission: "rejected",
		QualityScore:     0.95,
		ExpiresAt:        time.Now().Add(time.Hour),
	}, time.Now())
	reasons := fields["ineligibleReasons"].([]string)
	if !containsString(reasons, "quality_admission_not_approved") {
		t.Fatalf("reasons=%v must fail closed on admission", reasons)
	}
}

type stubPremiumPoolReader struct {
	items []rtrec.ContentCandidate
	calls int
}

func (s *stubPremiumPoolReader) ActivePremiumCandidates(context.Context, time.Time, int) ([]rtrec.ContentCandidate, error) {
	s.calls++
	out := make([]rtrec.ContentCandidate, len(s.items))
	copy(out, s.items)
	return out, nil
}

type stubCandidateSource struct {
	items []rtrec.ContentCandidate
	calls int
}

func (s *stubCandidateSource) Recall(context.Context, rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	s.calls++
	out := make([]rtrec.ContentCandidate, len(s.items))
	copy(out, s.items)
	return out, nil
}

func containsString(items []string, want string) bool {
	for _, item := range items {
		if item == want {
			return true
		}
	}
	return false
}
