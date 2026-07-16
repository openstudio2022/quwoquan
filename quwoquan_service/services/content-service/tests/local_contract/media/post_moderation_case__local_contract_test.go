package media_test

import (
	"context"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	moderationapp "quwoquan_service/services/content-service/internal/application/moderation"
	moderationmodel "quwoquan_service/services/content-service/internal/domain/moderation/model"
	mediacontract "quwoquan_service/services/content-service/internal/testsupport/media_contract"
)

func TestPostModerationWorkflowEligibilityAndIdempotency(t *testing.T) {
	now := time.Date(2030, time.March, 4, 5, 6, 7, 0, time.UTC)
	service, store := newModerationService(now)
	opened, err := service.OpenPostModerationCase(
		moderationContext("open-approved"),
		moderationapp.OpenPostModerationCaseCommand{
			PostID:        "post-1",
			PostVersion:   3,
			ContentDigest: "digest-v3",
		},
	)
	if err != nil {
		t.Fatalf("open moderation case: %v", err)
	}
	if opened.Status != moderationmodel.StatusPending || opened.Version != 1 {
		t.Fatalf("unexpected opened case: %+v", opened)
	}
	if _, err := service.DecidePostModerationCase(
		moderationContext("decide-before-review"),
		moderationapp.DecidePostModerationCaseCommand{
			CaseID:         opened.CaseID,
			ReviewerID:     "reviewer-1",
			Decision:       moderationmodel.DecisionApprove,
			DecisionReason: "safe",
		},
	); err == nil {
		t.Fatal("pending case must not skip reviewed transition")
	}
	pendingEligibility, err := service.GetPostPublicationEligibility(
		context.Background(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID: "post-1", PostVersion: 3, ContentDigest: "digest-v3",
		},
	)
	if err != nil {
		t.Fatalf("read pending eligibility: %v", err)
	}
	if pendingEligibility.Eligible || pendingEligibility.Moderation != moderationmodel.StatusPending {
		t.Fatalf("pending case must be ineligible: %+v", pendingEligibility)
	}

	reviewed, err := service.ReviewPostModerationCase(
		moderationContext("review-approved"),
		moderationapp.ReviewPostModerationCaseCommand{
			CaseID: opened.CaseID, ReviewerID: "reviewer-1",
		},
	)
	if err != nil {
		t.Fatalf("review moderation case: %v", err)
	}
	if reviewed.Status != moderationmodel.StatusReviewed || reviewed.Version != 2 {
		t.Fatalf("unexpected reviewed case: %+v", reviewed)
	}
	if _, err := service.DecidePostModerationCase(
		moderationContext("decide-wrong-reviewer"),
		moderationapp.DecidePostModerationCaseCommand{
			CaseID: opened.CaseID, ReviewerID: "reviewer-2",
			Decision: moderationmodel.DecisionApprove, DecisionReason: "safe",
		},
	); err == nil || !strings.Contains(err.Error(), "unauthorized") {
		t.Fatalf("different reviewer must be denied, got %v", err)
	}

	decisionContext := moderationContext("decide-approved")
	decided, err := service.DecidePostModerationCase(
		decisionContext,
		moderationapp.DecidePostModerationCaseCommand{
			CaseID: opened.CaseID, ReviewerID: "reviewer-1",
			Decision: moderationmodel.DecisionApprove, DecisionReason: "safe",
		},
	)
	if err != nil {
		t.Fatalf("approve moderation case: %v", err)
	}
	replayed, err := service.DecidePostModerationCase(
		decisionContext,
		moderationapp.DecidePostModerationCaseCommand{
			CaseID: opened.CaseID, ReviewerID: "reviewer-1",
			Decision: moderationmodel.DecisionApprove, DecisionReason: "safe",
		},
	)
	if err != nil {
		t.Fatalf("replay decision: %v", err)
	}
	if decided.Status != moderationmodel.StatusApproved ||
		decided.Version != 3 ||
		!replayed.Replayed ||
		replayed.Version != decided.Version {
		t.Fatalf("unexpected approved replay: decided=%+v replayed=%+v", decided, replayed)
	}
	approvedEligibility, err := service.GetPostPublicationEligibility(
		context.Background(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID: "post-1", PostVersion: 3, ContentDigest: "digest-v3",
		},
	)
	if err != nil {
		t.Fatalf("read approved eligibility: %v", err)
	}
	if !approvedEligibility.Eligible ||
		approvedEligibility.CaseID != opened.CaseID ||
		approvedEligibility.CaseVersion != 3 {
		t.Fatalf("approved current revision must be eligible: %+v", approvedEligibility)
	}
	staleEligibility, err := service.GetPostPublicationEligibility(
		context.Background(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID: "post-1", PostVersion: 4, ContentDigest: "digest-v4",
		},
	)
	if err != nil {
		t.Fatalf("read stale eligibility: %v", err)
	}
	if staleEligibility.Eligible {
		t.Fatalf("approval for old revision must not publish new revision: %+v", staleEligibility)
	}
	events := store.OutboxEvents()
	if len(events) != 3 ||
		events[0].AggregateVersion != 1 ||
		events[1].AggregateVersion != 2 ||
		events[2].AggregateVersion != 3 {
		t.Fatalf("idempotent moderation event dedup/version failed: %+v", events)
	}
	if len(store.AuditEntries()) != 3 {
		t.Fatalf("opened/reviewed/approved audit trail missing: %+v", store.AuditEntries())
	}
}

func TestRejectedPostRemainsPublicationIneligible(t *testing.T) {
	now := time.Date(2030, time.April, 5, 6, 7, 8, 0, time.UTC)
	service, _ := newModerationService(now)
	opened, err := service.OpenPostModerationCase(
		moderationContext("open-rejected"),
		moderationapp.OpenPostModerationCaseCommand{
			PostID: "post-reject", PostVersion: 1, ContentDigest: "digest-reject",
		},
	)
	if err != nil {
		t.Fatalf("open rejected case: %v", err)
	}
	if _, err := service.ReviewPostModerationCase(
		moderationContext("review-rejected"),
		moderationapp.ReviewPostModerationCaseCommand{
			CaseID: opened.CaseID, ReviewerID: "reviewer-3",
		},
	); err != nil {
		t.Fatalf("review rejected case: %v", err)
	}
	if _, err := service.DecidePostModerationCase(
		moderationContext("reject-case"),
		moderationapp.DecidePostModerationCaseCommand{
			CaseID: opened.CaseID, ReviewerID: "reviewer-3",
			Decision: moderationmodel.DecisionReject, DecisionReason: "policy",
		},
	); err != nil {
		t.Fatalf("reject moderation case: %v", err)
	}
	eligibility, err := service.GetPostPublicationEligibility(
		context.Background(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID: "post-reject", PostVersion: 1, ContentDigest: "digest-reject",
		},
	)
	if err != nil {
		t.Fatalf("read rejected eligibility: %v", err)
	}
	if eligibility.Eligible || eligibility.Moderation != moderationmodel.StatusRejected {
		t.Fatalf("rejected post must remain ineligible: %+v", eligibility)
	}
}

func newModerationService(
	now time.Time,
) (*moderationapp.ModerationService, *mediacontract.ModerationStore) {
	store := mediacontract.NewModerationStore()
	identifier := 0
	return moderationapp.NewModerationService(
		moderationapp.BindDataPorts(store),
		moderationapp.WithClock(func() time.Time { return now }),
		moderationapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			identifier++
			return prefix + "-" + string(rune('0'+identifier)), nil
		}),
	), store
}

func moderationContext(key string) context.Context {
	return commandmeta.WithIdempotencyKey(context.Background(), key)
}
