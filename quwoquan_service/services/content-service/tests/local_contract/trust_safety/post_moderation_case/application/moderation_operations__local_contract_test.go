// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-008
// readiness_case: open-post-moderation-case-local
// readiness_case: review-post-moderation-case-local
// readiness_case: decide-post-moderation-local
// readiness_case: supersede-post-moderation-case-local
// readiness_case: get-current-post-moderation-case-local
// readiness_case: get-post-publication-eligibility-local
package moderation_test

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	mediacontract "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport/media_contract"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
)

func TestPostModerationOperationsExecuteCanonicalApplicationFacades(t *testing.T) {
	t.Parallel()

	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	store := mediacontract.NewModerationStore()
	service := moderationapp.NewModerationService(
		moderationapp.BindDataPorts(store),
		moderationapp.WithClock(func() time.Time { return now }),
		moderationapp.WithIdentifierGenerator(func(string) (string, error) {
			return "pmc-readiness", nil
		}),
	)
	const (
		postID   = "post-moderation-readiness"
		reviewer = "reviewer-moderation-readiness"
		digest   = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	)

	opened, err := service.OpenPostModerationCase(
		moderationReadinessContext("open-moderation-readiness"),
		moderationapp.OpenPostModerationCaseCommand{
			PostID: postID, PostVersion: 7, ContentDigest: digest,
		},
	)
	if err != nil || opened.CaseID == "" || opened.Status != moderationmodel.StatusPending {
		t.Fatalf("open moderation case: result=%+v err=%v", opened, err)
	}

	current, err := service.GetCurrentPostModerationCase(
		context.Background(),
		moderationapp.GetCurrentPostModerationCaseQuery{PostID: postID},
	)
	if err != nil || current.ID != opened.CaseID || current.Status != moderationmodel.StatusPending {
		t.Fatalf("get current moderation case: result=%+v err=%v", current, err)
	}

	reviewed, err := service.ReviewPostModerationCase(
		moderationReadinessContext("review-moderation-readiness"),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID: postID, CaseID: opened.CaseID, ReviewerID: reviewer,
		},
	)
	if err != nil || reviewed.Status != moderationmodel.StatusReviewed {
		t.Fatalf("review moderation case: result=%+v err=%v", reviewed, err)
	}

	decided, err := service.DecidePostModerationCase(
		moderationReadinessContext("decide-moderation-readiness"),
		moderationapp.DecidePostModerationCaseCommand{
			PostID: postID, CaseID: opened.CaseID, ReviewerID: reviewer,
			Decision: moderationmodel.DecisionApprove, DecisionReason: "policy review passed",
		},
	)
	if err != nil || decided.Status != moderationmodel.StatusApproved {
		t.Fatalf("decide moderation case: result=%+v err=%v", decided, err)
	}

	eligibility, err := service.GetPostPublicationEligibility(
		context.Background(),
		moderationapp.GetPostPublicationEligibilityQuery{
			PostID: postID, PostVersion: 7, ContentDigest: digest,
		},
	)
	if err != nil || !eligibility.Eligible || eligibility.CaseID != opened.CaseID {
		t.Fatalf("get publication eligibility: result=%+v err=%v", eligibility, err)
	}

	superseded, err := service.SupersedePostModerationCase(
		moderationReadinessContext("supersede-moderation-readiness"),
		moderationapp.SupersedePostModerationCaseCommand{
			PostID: postID, CaseID: opened.CaseID,
		},
	)
	if err != nil || superseded.Status != moderationmodel.StatusSuperseded {
		t.Fatalf("supersede moderation case: result=%+v err=%v", superseded, err)
	}
}

func moderationReadinessContext(key string) context.Context {
	return commandmeta.WithIdempotencyKey(context.Background(), key)
}
