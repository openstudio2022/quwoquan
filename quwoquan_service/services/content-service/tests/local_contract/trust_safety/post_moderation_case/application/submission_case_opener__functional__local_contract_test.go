// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-008
// readiness_case: open-post-moderation-case-events-local
package moderation_test

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	. "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

func TestPostSubmissionModerationHandlerExecutesCanonicalCommandAndAcknowledgesEvent(t *testing.T) {
	commands := &recordingModerationCommands{}
	handler := NewPostSubmissionModerationHandler(commands)
	event := postports.OutboxEvent{
		EventID: "post-submitted-event-1", EventType: "PostSubmittedForReview",
		AggregateType: "Post", AggregateID: "post-under-review", AggregateVersion: 7,
		Payload:    []byte(`{"postId":"post-under-review","status":"pending_review","moderationStatus":"pending","contentDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`),
		OccurredAt: time.Date(2030, time.January, 2, 3, 4, 5, 0, time.UTC),
	}

	if err := handler.OpenPostModerationCase(context.Background(), event); err != nil {
		t.Fatalf("apply PostSubmittedForReview: %v", err)
	}
	if commands.openCalls != 1 {
		t.Fatalf("open moderation calls=%d, want 1", commands.openCalls)
	}
	if commands.open.PostID != event.AggregateID || commands.open.PostVersion != event.AggregateVersion ||
		commands.open.ContentDigest != "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" {
		t.Fatalf("opened moderation command drifted: %+v", commands.open)
	}
	if commands.idempotencyKey != "post-submission-moderation:"+event.EventID {
		t.Fatalf("server idempotency=%q", commands.idempotencyKey)
	}
}

func TestReportModerationHandlerExecutesCanonicalCommand(t *testing.T) {
	commands := &recordingModerationCommands{}
	handler := NewReportModerationHandler(commands, staticPostRevisionReader{
		revision: postports.PostRevisionSlice{
			PostID:        postports.NewPostID("reported-post"),
			Version:       5,
			ContentDigest: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		},
	})
	event := reportports.OutboxEvent{
		EventID:   "report-created-event-1",
		EventType: "content.report.ReportCreated",
		Payload:   []byte(`{"reportId":"report-1","targetType":"post","targetId":"reported-post"}`),
	}
	if err := handler.OpenPostModerationCase(context.Background(), event); err != nil {
		t.Fatalf("apply ReportCreated: %v", err)
	}
	if commands.openCalls != 1 || commands.open.PostID != "reported-post" ||
		commands.open.PostVersion != 5 ||
		commands.open.ContentDigest != "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" {
		t.Fatalf("report moderation command drifted: calls=%d command=%+v", commands.openCalls, commands.open)
	}
	if commands.idempotencyKey != "report-moderation:report-1" {
		t.Fatalf("report moderation idempotency=%q", commands.idempotencyKey)
	}
}

type staticPostRevisionReader struct {
	revision postports.PostRevisionSlice
}

func (reader staticPostRevisionReader) FindPostRevision(
	_ context.Context,
	postID postports.PostID,
) (postports.PostRevisionSlice, bool, error) {
	if postID != reader.revision.PostID {
		return postports.PostRevisionSlice{}, false, nil
	}
	return reader.revision, true, nil
}

type recordingModerationCommands struct {
	openCalls      int
	open           OpenPostModerationCaseCommand
	idempotencyKey string
}

func (commands *recordingModerationCommands) OpenPostModerationCase(
	ctx context.Context,
	command OpenPostModerationCaseCommand,
) (PostModerationCaseCommandResult, error) {
	commands.openCalls++
	commands.open = command
	commands.idempotencyKey = commandmeta.IdempotencyKey(ctx)
	return PostModerationCaseCommandResult{}, nil
}

func (*recordingModerationCommands) ReviewPostModerationCase(
	context.Context,
	ReviewPostModerationCaseCommand,
) (PostModerationCaseCommandResult, error) {
	panic("unexpected ReviewPostModerationCase")
}

func (*recordingModerationCommands) DecidePostModerationCase(
	context.Context,
	DecidePostModerationCaseCommand,
) (PostModerationCaseCommandResult, error) {
	panic("unexpected DecidePostModerationCase")
}

func (*recordingModerationCommands) SupersedePostModerationCase(
	context.Context,
	SupersedePostModerationCaseCommand,
) (PostModerationCaseCommandResult, error) {
	panic("unexpected SupersedePostModerationCase")
}
