package media_test

import (
	"context"
	"testing"
	"time"

	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
)

func TestPendingPublicationOpensCaseAndApprovalPublishesExactRevision(t *testing.T) {
	postStore := testsupport.NewPostStore(nil)
	postService := postapp.NewPostService(
		postapp.BindDataPorts(postStore),
		postapp.WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{
				Decision: postports.PublicationSafetyReview,
			},
		),
	)
	command := postapp.SubmitPostPublicationCommand{
		PublishIntentID: "intent-prepublication-review",
		LocalDraftID:    "draft-prepublication-review",
		AuthorID:        "persona-prepublication-review",
		Content: postmodel.Post{
			ContentType: "micro",
			Body:        "这是一条必须先审核再公开的文字内容。",
			Visibility:  "public",
		},
	}
	receipt, err := postService.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			command.PublishIntentID,
		),
		command,
	)
	if err != nil {
		t.Fatalf("submit pending publication: %v", err)
	}
	if receipt.State != "pending_review" || receipt.CommittedVersion != 1 {
		t.Fatalf("pending receipt mismatch: %+v", receipt)
	}
	if visible := postStore.ListPublished(context.Background(), 10, ""); len(visible) != 0 {
		t.Fatalf("pending Post leaked before moderation: %+v", visible)
	}

	decisionAt := receipt.AcceptedAt.Add(time.Minute)
	moderationService, moderationStore := newModerationService(decisionAt)
	submissionRelay := postapp.NewOutboxRelay(
		postStore,
		postStore,
		moderationapp.NewSubmissionCaseOpener(moderationService),
		"content-post-submission-moderation-test",
	)
	delivered, err := submissionRelay.Drain(context.Background(), 10)
	if err != nil || delivered != 1 {
		t.Fatalf("pending submission did not open moderation case: delivered=%d err=%v", delivered, err)
	}
	replayRelay := postapp.NewOutboxRelay(
		postStore,
		postStore,
		moderationapp.NewSubmissionCaseOpener(moderationService),
		"content-post-submission-moderation-replay-test",
	)
	if replayed, replayErr := replayRelay.Drain(
		context.Background(),
		10,
	); replayErr != nil || replayed != 1 || len(moderationStore.OutboxEvents()) != 1 {
		t.Fatalf(
			"submission replay created a duplicate case: delivered=%d outbox=%+v err=%v",
			replayed,
			moderationStore.OutboxEvents(),
			replayErr,
		)
	}
	caseSlice, err := moderationService.GetCurrentPostModerationCase(
		context.Background(),
		moderationapp.GetCurrentPostModerationCaseQuery{PostID: receipt.PostID},
	)
	if err != nil {
		t.Fatalf("read moderation case: %v", err)
	}
	if caseSlice.PostVersion != receipt.CommittedVersion ||
		caseSlice.ContentDigest == "" ||
		caseSlice.Status != moderationmodel.StatusPending {
		t.Fatalf("moderation case revision mismatch: %+v", caseSlice)
	}

	reviewerID := "operator-prepublication-review"
	if _, err := moderationService.ReviewPostModerationCase(
		moderationContext("review-prepublication-case"),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID: receipt.PostID, CaseID: caseSlice.ID, ReviewerID: reviewerID,
		},
	); err != nil {
		t.Fatalf("review moderation case: %v", err)
	}
	if _, err := moderationService.DecidePostModerationCase(
		moderationContext("approve-prepublication-case"),
		moderationapp.DecidePostModerationCaseCommand{
			PostID:         receipt.PostID,
			CaseID:         caseSlice.ID,
			ReviewerID:     reviewerID,
			Decision:       moderationmodel.DecisionApprove,
			DecisionReason: "内容安全",
		},
	); err != nil {
		t.Fatalf("approve moderation case: %v", err)
	}

	decisionRelay := moderationapp.NewOutboxRelay(
		moderationStore,
		moderationStore,
		postapp.NewPostModerationDecisionConsumer(postService),
		"content-moderation-post-lifecycle-test",
	)
	delivered, err = decisionRelay.Drain(context.Background(), 10)
	if err != nil || delivered != 3 {
		t.Fatalf("moderation decision did not reach Post: delivered=%d err=%v", delivered, err)
	}
	published, found, err := postStore.Load(context.Background(), receipt.PostID)
	if err != nil || !found {
		t.Fatalf("load approved Post: found=%v err=%v", found, err)
	}
	if published.Version != receipt.CommittedVersion+1 ||
		published.Status != "published" ||
		published.ModerationStatus != "approved" ||
		published.PublishedAt.IsZero() {
		t.Fatalf("approved Post lifecycle mismatch: %+v", published)
	}
	if visible := postStore.ListPublished(context.Background(), 10, ""); len(visible) != 1 {
		t.Fatalf("approved Post did not enter public read source: %+v", visible)
	}
}

func TestPendingPublicationRejectionNeverEntersPublicReadModel(t *testing.T) {
	postStore := testsupport.NewPostStore(nil)
	postService := postapp.NewPostService(
		postapp.BindDataPorts(postStore),
		postapp.WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{
				Decision: postports.PublicationSafetyReview,
			},
		),
	)
	command := postapp.SubmitPostPublicationCommand{
		PublishIntentID: "intent-prepublication-reject",
		LocalDraftID:    "draft-prepublication-reject",
		AuthorID:        "persona-prepublication-reject",
		Content: postmodel.Post{
			ContentType: "micro",
			Body:        "这是一条审核拒绝后不得公开的文字内容。",
			Visibility:  "public",
		},
	}
	receipt, err := postService.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			command.PublishIntentID,
		),
		command,
	)
	if err != nil || receipt.State != "pending_review" {
		t.Fatalf("submit pending publication: receipt=%+v err=%v", receipt, err)
	}

	moderationService, moderationStore := newModerationService(
		receipt.AcceptedAt.Add(time.Minute),
	)
	submissionRelay := postapp.NewOutboxRelay(
		postStore,
		postStore,
		moderationapp.NewSubmissionCaseOpener(moderationService),
		"content-post-submission-rejection-test",
	)
	if delivered, relayErr := submissionRelay.Drain(
		context.Background(),
		10,
	); relayErr != nil || delivered != 1 {
		t.Fatalf("open rejection case: delivered=%d err=%v", delivered, relayErr)
	}
	caseSlice, err := moderationService.GetCurrentPostModerationCase(
		context.Background(),
		moderationapp.GetCurrentPostModerationCaseQuery{PostID: receipt.PostID},
	)
	if err != nil {
		t.Fatalf("read rejection case: %v", err)
	}
	reviewerID := "operator-prepublication-reject"
	if _, err := moderationService.ReviewPostModerationCase(
		moderationContext("review-prepublication-rejection"),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID: receipt.PostID, CaseID: caseSlice.ID, ReviewerID: reviewerID,
		},
	); err != nil {
		t.Fatalf("review rejection case: %v", err)
	}
	if _, err := moderationService.DecidePostModerationCase(
		moderationContext("reject-prepublication-case"),
		moderationapp.DecidePostModerationCaseCommand{
			PostID:         receipt.PostID,
			CaseID:         caseSlice.ID,
			ReviewerID:     reviewerID,
			Decision:       moderationmodel.DecisionReject,
			DecisionReason: "违反内容安全规则",
		},
	); err != nil {
		t.Fatalf("reject moderation case: %v", err)
	}
	decisionRelay := moderationapp.NewOutboxRelay(
		moderationStore,
		moderationStore,
		postapp.NewPostModerationDecisionConsumer(postService),
		"content-moderation-post-rejection-test",
	)
	if delivered, relayErr := decisionRelay.Drain(
		context.Background(),
		10,
	); relayErr != nil || delivered != 3 {
		t.Fatalf("apply rejection to Post: delivered=%d err=%v", delivered, relayErr)
	}
	rejected, found, err := postStore.Load(context.Background(), receipt.PostID)
	if err != nil || !found {
		t.Fatalf("load rejected Post: found=%v err=%v", found, err)
	}
	if rejected.Status != "rejected" ||
		rejected.ModerationStatus != "rejected" ||
		!rejected.PublishedAt.IsZero() {
		t.Fatalf("rejected Post lifecycle mismatch: %+v", rejected)
	}
	if visible := postStore.ListPublished(context.Background(), 10, ""); len(visible) != 0 {
		t.Fatalf("rejected Post leaked into public read source: %+v", visible)
	}
	events := postStore.OutboxEvents()
	if len(events) != 2 || events[1].EventType != "PostModerationRejected" {
		t.Fatalf("rejected Post event mismatch: %+v", events)
	}
}
