package media_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	mediacontract "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport/media_contract"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
	moderationports "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/ports"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
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
	current, err := service.GetCurrentPostModerationCase(
		context.Background(),
		moderationapp.GetCurrentPostModerationCaseQuery{PostID: "post-1"},
	)
	if err != nil {
		t.Fatalf("read current moderation case: %v", err)
	}
	if current.ID != opened.CaseID ||
		current.PostVersion != 3 ||
		current.Status != moderationmodel.StatusPending {
		t.Fatalf("unexpected current moderation case: %+v", current)
	}
	if _, err := service.DecidePostModerationCase(
		moderationContext("decide-before-review"),
		moderationapp.DecidePostModerationCaseCommand{
			PostID:         "post-1",
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
			PostID: "post-1", CaseID: opened.CaseID, ReviewerID: "reviewer-1",
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
			PostID: "post-1", CaseID: opened.CaseID, ReviewerID: "reviewer-2",
			Decision: moderationmodel.DecisionApprove, DecisionReason: "safe",
		},
	); err == nil || !strings.Contains(err.Error(), "unauthorized") {
		t.Fatalf("different reviewer must be denied, got %v", err)
	}

	decisionContext := moderationContext("decide-approved")
	decided, err := service.DecidePostModerationCase(
		decisionContext,
		moderationapp.DecidePostModerationCaseCommand{
			PostID: "post-1", CaseID: opened.CaseID, ReviewerID: "reviewer-1",
			Decision: moderationmodel.DecisionApprove, DecisionReason: "safe",
		},
	)
	if err != nil {
		t.Fatalf("approve moderation case: %v", err)
	}
	replayed, err := service.DecidePostModerationCase(
		decisionContext,
		moderationapp.DecidePostModerationCaseCommand{
			PostID: "post-1", CaseID: opened.CaseID, ReviewerID: "reviewer-1",
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
			PostID: "post-reject", CaseID: opened.CaseID, ReviewerID: "reviewer-3",
		},
	); err != nil {
		t.Fatalf("review rejected case: %v", err)
	}
	if _, err := service.DecidePostModerationCase(
		moderationContext("reject-case"),
		moderationapp.DecidePostModerationCaseCommand{
			PostID: "post-reject", CaseID: opened.CaseID, ReviewerID: "reviewer-3",
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

func TestReportRevisionReadFailureKeepsOutboxCheckpointReplayable(t *testing.T) {
	now := time.Date(2030, time.May, 6, 7, 8, 9, 0, time.UTC)
	moderationService, _ := newModerationService(now)
	reportStore := testsupport.NewReportStore()
	report, err := reportmodel.Create(reportmodel.CreateParams{
		ID:                "report-reader-failure",
		ReporterID:        "reporter-reader-failure",
		ReporterAccountID: "account-reporter-reader-failure",
		TargetType:        reportmodel.TargetPost,
		TargetID:          "post-corrupt-revision",
		Reason:            reportmodel.ReasonSpam,
		Description:       "reader failure must keep checkpoint replayable",
		Now:               now,
	})
	if err != nil {
		t.Fatalf("create report fixture: %v", err)
	}
	payload, err := json.Marshal(map[string]string{
		"reportId":   report.ID(),
		"targetType": "post",
		"targetId":   "post-corrupt-revision",
	})
	if err != nil {
		t.Fatalf("encode report fact: %v", err)
	}
	if _, err := reportStore.Commit(context.Background(), reportports.Commit{
		Aggregate:        report,
		ExpectedVersion:  0,
		IdempotencyKey:   "report-reader-failure",
		CommandName:      "CreateReport",
		CommandDigest:    "digest-reader-failure",
		ReceiptExpiresAt: now.Add(time.Hour),
		Events: []reportports.OutboxEvent{{
			EventID:          "event-reader-failure",
			EventType:        "content.report.created",
			AggregateID:      report.ID(),
			AggregateVersion: report.Version(),
			Payload:          payload,
			OccurredAt:       now,
		}},
	}); err != nil {
		t.Fatalf("persist report fact: %v", err)
	}

	opener := moderationapp.NewReportCaseOpener(
		moderationService,
		failingPostRevisionReader{err: errors.New("malformed Mongo revision")},
	)
	relay := reportapp.NewOutboxRelay(
		reportStore,
		reportStore,
		opener,
		"content-report-moderation-reader-failure",
	)
	delivered, err := relay.Drain(context.Background(), 10)
	if err == nil || !strings.Contains(err.Error(), "malformed Mongo revision") {
		t.Fatalf("reader failure must propagate through relay, delivered=%d err=%v", delivered, err)
	}
	if delivered != 0 {
		t.Fatalf("failed reader must commit zero facts, got %d", delivered)
	}
	lease, acquired, err := reportStore.AcquireCheckpoint(
		context.Background(),
		"content-report-moderation-reader-failure",
	)
	if err != nil || !acquired {
		t.Fatalf("reacquire failed checkpoint: acquired=%v err=%v", acquired, err)
	}
	if checkpoint := lease.Checkpoint(); checkpoint != "" {
		t.Fatalf("reader failure advanced checkpoint to %q", checkpoint)
	}
	if err := lease.Rollback(); err != nil {
		t.Fatalf("rollback checkpoint probe: %v", err)
	}
}

func TestModerationDecisionConsumerAppliesExactPostRevisionAndVisibility(t *testing.T) {
	now := time.Date(2030, time.June, 7, 8, 9, 10, 0, time.UTC)
	store := testsupport.NewPostStore([]postmodel.Post{{
		ID:               "post-moderation-target",
		Version:          1,
		AuthorId:         "author-moderation",
		Status:           "published",
		Visibility:       "public",
		ModerationStatus: "approved",
		ContentDigest:    "digest-moderation-target",
		CreatedAt:        now.Add(-time.Hour),
		UpdatedAt:        now.Add(-time.Hour),
		PublishedAt:      now.Add(-time.Hour),
	}})
	service := postapp.NewPostService(postapp.BindDataPorts(store))
	consumer := postapp.NewPostModerationDecisionConsumer(service)

	rejected := moderationDecisionEvent(
		t,
		"event-post-rejected",
		"case-post-rejected",
		3,
		"post-moderation-target",
		1,
		"digest-moderation-target",
		"rejected",
		now,
	)
	if err := consumer.Publish(context.Background(), rejected); err != nil {
		t.Fatalf("apply rejected decision: %v", err)
	}
	post, found, err := store.Load(context.Background(), "post-moderation-target")
	if err != nil || !found {
		t.Fatalf("load rejected Post: found=%v err=%v", found, err)
	}
	if post.Version != 2 || post.ModerationStatus != "rejected" {
		t.Fatalf("rejected decision not committed once: %+v", post)
	}
	if visible := store.ListPublished(context.Background(), 10, ""); len(visible) != 0 {
		t.Fatalf("rejected Post leaked into published/search source: %+v", visible)
	}

	if err := consumer.Publish(context.Background(), rejected); err != nil {
		t.Fatalf("replay rejected decision: %v", err)
	}
	replayed, _, _ := store.Load(context.Background(), "post-moderation-target")
	if replayed.Version != 2 || len(store.OutboxEvents()) != 1 {
		t.Fatalf("decision replay must be a target-state no-op: post=%+v outbox=%+v", replayed, store.OutboxEvents())
	}

	staleApproval := moderationDecisionEvent(
		t,
		"event-post-stale-approval",
		"case-post-stale-approval",
		3,
		"post-moderation-target",
		1,
		"digest-moderation-target",
		"approved",
		now.Add(time.Minute),
	)
	if err := consumer.Publish(context.Background(), staleApproval); err != nil {
		t.Fatalf("stale approval must be an acknowledged no-op: %v", err)
	}
	stale, _, _ := store.Load(context.Background(), "post-moderation-target")
	if stale.Version != 2 || stale.ModerationStatus != "rejected" {
		t.Fatalf("stale approval overwrote newer Post revision: %+v", stale)
	}

	approved := moderationDecisionEvent(
		t,
		"event-post-approved",
		"case-post-approved",
		3,
		"post-moderation-target",
		2,
		"digest-moderation-target",
		"approved",
		now.Add(2*time.Minute),
	)
	if err := consumer.Publish(context.Background(), approved); err != nil {
		t.Fatalf("apply exact-revision approval: %v", err)
	}
	restored, _, _ := store.Load(context.Background(), "post-moderation-target")
	if restored.Version != 3 || restored.ModerationStatus != "approved" {
		t.Fatalf("approval did not restore publication eligibility: %+v", restored)
	}
	if visible := store.ListPublished(context.Background(), 10, ""); len(visible) != 1 {
		t.Fatalf("approved Post was not restored to published/search source: %+v", visible)
	}
}

func TestConcurrentModerationCommandsConvergeToSingleTargetTransitions(t *testing.T) {
	now := time.Date(2030, time.July, 8, 9, 10, 11, 0, time.UTC)
	service, store := newModerationService(now)
	const workers = 8

	openResults := runModerationCommands(workers, func(index int) (moderationapp.PostModerationCaseCommandResult, error) {
		return service.OpenPostModerationCase(
			moderationContext(fmt.Sprintf("concurrent-open-%d", index)),
			moderationapp.OpenPostModerationCaseCommand{
				PostID: "post-concurrent", PostVersion: 9, ContentDigest: "digest-concurrent",
			},
		)
	})
	caseID := ""
	for _, outcome := range openResults {
		if outcome.err != nil {
			t.Fatalf("concurrent Open failed: %v", outcome.err)
		}
		if caseID == "" {
			caseID = outcome.result.CaseID
		}
		if outcome.result.CaseID != caseID || outcome.result.Status != moderationmodel.StatusPending {
			t.Fatalf("concurrent Open diverged: %+v", outcome.result)
		}
	}

	reviewResults := runModerationCommands(workers, func(index int) (moderationapp.PostModerationCaseCommandResult, error) {
		return service.ReviewPostModerationCase(
			moderationContext(fmt.Sprintf("concurrent-review-%d", index)),
			moderationapp.ReviewPostModerationCaseCommand{
				PostID: "post-concurrent", CaseID: caseID, ReviewerID: "reviewer-concurrent",
			},
		)
	})
	for _, outcome := range reviewResults {
		if outcome.err != nil || outcome.result.Status != moderationmodel.StatusReviewed {
			t.Fatalf("concurrent Review did not converge: result=%+v err=%v", outcome.result, outcome.err)
		}
	}

	decideResults := runModerationCommands(workers, func(index int) (moderationapp.PostModerationCaseCommandResult, error) {
		return service.DecidePostModerationCase(
			moderationContext(fmt.Sprintf("concurrent-decide-%d", index)),
			moderationapp.DecidePostModerationCaseCommand{
				PostID:         "post-concurrent",
				CaseID:         caseID,
				ReviewerID:     "reviewer-concurrent",
				Decision:       moderationmodel.DecisionApprove,
				DecisionReason: "same target",
			},
		)
	})
	for _, outcome := range decideResults {
		if outcome.err != nil || outcome.result.Status != moderationmodel.StatusApproved {
			t.Fatalf("concurrent Decide did not converge: result=%+v err=%v", outcome.result, outcome.err)
		}
	}

	supersedeResults := runModerationCommands(workers, func(index int) (moderationapp.PostModerationCaseCommandResult, error) {
		return service.SupersedePostModerationCase(
			moderationContext(fmt.Sprintf("concurrent-supersede-%d", index)),
			moderationapp.SupersedePostModerationCaseCommand{
				PostID: "post-concurrent", CaseID: caseID,
			},
		)
	})
	for _, outcome := range supersedeResults {
		if outcome.err != nil || outcome.result.Status != moderationmodel.StatusSuperseded {
			t.Fatalf("concurrent Supersede did not converge: result=%+v err=%v", outcome.result, outcome.err)
		}
	}
	if events := store.OutboxEvents(); len(events) != 4 {
		t.Fatalf("target transitions must emit exactly open/review/decide/supersede: %+v", events)
	}
	if audits := store.AuditEntries(); len(audits) != 4 {
		t.Fatalf("target transitions must audit exactly once: %+v", audits)
	}
}

type failingPostRevisionReader struct {
	err error
}

func (r failingPostRevisionReader) FindPostRevision(
	context.Context,
	postports.PostID,
) (postports.PostRevisionSlice, bool, error) {
	return postports.PostRevisionSlice{}, false, r.err
}

func moderationDecisionEvent(
	t *testing.T,
	eventID string,
	caseID string,
	caseVersion int64,
	postID string,
	postVersion int64,
	digest string,
	status string,
	decidedAt time.Time,
) moderationports.OutboxEvent {
	t.Helper()
	payload, err := json.Marshal(map[string]any{
		"id":            caseID,
		"version":       caseVersion,
		"postId":        postID,
		"postVersion":   postVersion,
		"contentDigest": digest,
		"reviewerId":    "reviewer-post-lifecycle",
		"status":        status,
		"decidedAt":     decidedAt.UTC(),
	})
	if err != nil {
		t.Fatalf("encode moderation decision: %v", err)
	}
	return moderationports.OutboxEvent{
		EventID:          eventID,
		EventType:        "content.post_moderation_case.decided",
		AggregateID:      caseID,
		AggregateVersion: caseVersion,
		Payload:          payload,
		OccurredAt:       decidedAt.UTC(),
		Checkpoint:       decidedAt.UTC().Format(time.RFC3339Nano) + "|" + eventID,
	}
}

type moderationCommandOutcome struct {
	result moderationapp.PostModerationCaseCommandResult
	err    error
}

func runModerationCommands(
	count int,
	command func(index int) (moderationapp.PostModerationCaseCommandResult, error),
) []moderationCommandOutcome {
	outcomes := make([]moderationCommandOutcome, count)
	var wait sync.WaitGroup
	wait.Add(count)
	for index := 0; index < count; index++ {
		go func(index int) {
			defer wait.Done()
			outcomes[index].result, outcomes[index].err = command(index)
		}(index)
	}
	wait.Wait()
	return outcomes
}

func newModerationService(
	now time.Time,
) (*moderationapp.ModerationService, *mediacontract.ModerationStore) {
	store := mediacontract.NewModerationStore()
	var identifier atomic.Int64
	return moderationapp.NewModerationService(
		moderationapp.BindDataPorts(store),
		moderationapp.WithClock(func() time.Time { return now }),
		moderationapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			return fmt.Sprintf("%s-%d", prefix, identifier.Add(1)), nil
		}),
	), store
}

func moderationContext(key string) context.Context {
	return commandmeta.WithIdempotencyKey(context.Background(), key)
}
