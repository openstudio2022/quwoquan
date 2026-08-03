package recommendation_test

// N0-3 契约：服务端权威信号投影语义。
//  - ContentReactionSet(like, post) → BehaviorSignal{action=like}，进 HotPath 与持久轨；
//  - ContentReactionCleared / 非 like / 非 post 不产生信号（unlike 无负信号）；
//  - CommentCreated → action=comment；content.report.created(post) → action=report；
//  - clientEventId 使用 "authoritative:"+EventID（确定性，唯一索引兜底重放幂等）。

import (
	"context"
	"encoding/json"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

type capturedSignals struct {
	batches [][]rtrec.BehaviorSignal
}

func (c *capturedSignals) ProcessSignal(ctx context.Context, signal rtrec.BehaviorSignal) error {
	return c.ProcessSignalBatch(ctx, []rtrec.BehaviorSignal{signal})
}

func (c *capturedSignals) ProcessSignalBatch(_ context.Context, signals []rtrec.BehaviorSignal) error {
	c.batches = append(c.batches, signals)
	return nil
}

type capturedEvents struct {
	events []ports.RawBehaviorEvent
}

func (c *capturedEvents) InsertBatch(_ context.Context, events []ports.RawBehaviorEvent) error {
	c.events = append(c.events, events...)
	return nil
}

func (c *capturedEvents) ListUserFootprint(context.Context, string, []string, time.Time, int) ([]ports.RawBehaviorEvent, error) {
	return nil, nil
}

func testSink() (*AuthoritativeSignalSink, *capturedSignals, *capturedEvents) {
	signals := &capturedSignals{}
	events := &capturedEvents{}
	sink := NewAuthoritativeSignalSink(nil, signals, events)
	return sink, signals, events
}

func mustJSON(t *testing.T, v any) []byte {
	t.Helper()
	payload, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal fact: %v", err)
	}
	return payload
}

func TestReactionSignalProjector_LikeSetProducesLikeSignal(t *testing.T) {
	sink, signals, events := testSink()
	projector := NewReactionSignalProjector(sink)

	payload := mustJSON(t, map[string]any{
		"targetKind":     "post",
		"targetId":       "post_1",
		"targetAuthorId": "author_1",
		"actorId":        "user_1",
		"reaction":       "like",
		"occurredAt":     time.Now().UTC().Format(time.RFC3339),
	})
	err := projector.Publish(context.Background(), reactionports.OutboxFact{
		EventID:   "reaction:r1:1",
		EventType: "ContentReactionSet",
		Payload:   payload,
	})
	if err != nil {
		t.Fatalf("publish like fact: %v", err)
	}

	if len(signals.batches) != 1 || len(signals.batches[0]) != 1 {
		t.Fatalf("expected 1 hotpath signal, got %+v", signals.batches)
	}
	got := signals.batches[0][0]
	if got.Action != "like" || got.UserID != "user_1" || got.ContentID != "post_1" {
		t.Fatalf("unexpected signal: %+v", got)
	}
	if got.AuthorID != "author_1" {
		t.Fatalf("author fallback from fact targetAuthorId failed: %+v", got)
	}
	if got.ClientEventID != "authoritative:reaction:r1:1" {
		t.Fatalf("clientEventId must be deterministic, got %s", got.ClientEventID)
	}
	if len(events.events) != 1 || events.events[0].Action != "like" {
		t.Fatalf("expected like event persisted to behavior track, got %+v", events.events)
	}
}

func TestReactionSignalProjector_ClearedAndNonLikeIgnored(t *testing.T) {
	sink, signals, _ := testSink()
	projector := NewReactionSignalProjector(sink)

	cleared := reactionports.OutboxFact{
		EventID:   "reaction:r2:2",
		EventType: "ContentReactionCleared",
		Payload:   mustJSON(t, map[string]any{"targetKind": "post", "targetId": "p", "actorId": "u", "reaction": ""}),
	}
	commentLike := reactionports.OutboxFact{
		EventID:   "reaction:r3:1",
		EventType: "ContentReactionSet",
		Payload:   mustJSON(t, map[string]any{"targetKind": "comment", "targetId": "c", "actorId": "u", "reaction": "like"}),
	}
	for _, fact := range []reactionports.OutboxFact{cleared, commentLike} {
		if err := projector.Publish(context.Background(), fact); err != nil {
			t.Fatalf("publish %s: %v", fact.EventType, err)
		}
	}
	if len(signals.batches) != 0 {
		t.Fatalf("cleared/comment-target facts must not produce signals, got %+v", signals.batches)
	}
}

func TestAuthoritativeSignalPersistsCanonicalBehaviorWithoutFeedRequestID(t *testing.T) {
	sink, signals, events := testSink()

	if err := sink.Emit(context.Background(), rtrec.BehaviorSignal{
		UserID: "user_1", SessionID: "outbox-session", ContentID: "post_1",
		Action: "like", ClientEventID: "authoritative:reaction:r1:1",
	}); err != nil {
		t.Fatalf("unattributed authoritative signal must remain processable: %v", err)
	}
	if len(signals.batches) != 1 || len(events.events) != 1 {
		t.Fatalf(
			"unattributed authoritative signal must preserve HotPath and behavior projection: signals=%+v events=%+v",
			signals.batches,
			events.events,
		)
	}
}

func TestCommentSignalProjector_CommentCreatedProducesCommentSignal(t *testing.T) {
	sink, signals, events := testSink()
	projector := NewCommentSignalProjector(sink)

	err := projector.Publish(context.Background(), commentports.OutboxEvent{
		EventID:   "comment:c1:1",
		EventType: "CommentCreated",
		Payload: mustJSON(t, map[string]any{
			"commentId":    "c1",
			"postId":       "post_9",
			"postAuthorId": "author_9",
			"authorId":     "commenter_1",
			"createdAt":    time.Now().UTC().Format(time.RFC3339),
		}),
	})
	if err != nil {
		t.Fatalf("publish comment fact: %v", err)
	}
	if len(signals.batches) != 1 {
		t.Fatalf("expected comment signal, got %+v", signals.batches)
	}
	got := signals.batches[0][0]
	if got.Action != "comment" || got.UserID != "commenter_1" || got.ContentID != "post_9" || got.AuthorID != "author_9" {
		t.Fatalf("unexpected comment signal: %+v", got)
	}
	if len(events.events) != 1 || events.events[0].Action != "comment" {
		t.Fatalf("comment event not persisted: %+v", events.events)
	}
}

func TestReportSignalProjector_PostReportProducesNegativeSignal(t *testing.T) {
	sink, signals, events := testSink()
	projector := NewReportSignalProjector(sink)

	occurred := time.Now().UTC()
	err := projector.Publish(context.Background(), reportports.OutboxEvent{
		EventID:    "report:rpt1:1",
		EventType:  "content.report.created",
		OccurredAt: occurred,
		Payload: mustJSON(t, map[string]any{
			"reportId":   "rpt1",
			"reporterId": "user_2",
			"targetType": "post",
			"targetId":   "post_5",
			"reason":     "spam",
		}),
	})
	if err != nil {
		t.Fatalf("publish report fact: %v", err)
	}
	if len(signals.batches) != 1 {
		t.Fatalf("expected report signal, got %+v", signals.batches)
	}
	got := signals.batches[0][0]
	if got.Action != "report" || got.UserID != "user_2" || got.ContentID != "post_5" {
		t.Fatalf("unexpected report signal: %+v", got)
	}
	if !got.Timestamp.Equal(occurred) {
		t.Fatalf("report signal timestamp must come from fact OccurredAt, got %v", got.Timestamp)
	}
	if len(events.events) != 1 || events.events[0].Action != "report" {
		t.Fatalf("report event not persisted: %+v", events.events)
	}
}

func TestReportSignalProjector_NonPostTargetIgnored(t *testing.T) {
	sink, signals, _ := testSink()
	projector := NewReportSignalProjector(sink)

	err := projector.Publish(context.Background(), reportports.OutboxEvent{
		EventID:   "report:rpt2:1",
		EventType: "content.report.created",
		Payload: mustJSON(t, map[string]any{
			"reportId":   "rpt2",
			"reporterId": "user_2",
			"targetType": "comment",
			"targetId":   "c_5",
		}),
	})
	if err != nil {
		t.Fatalf("publish non-post report: %v", err)
	}
	if len(signals.batches) != 0 {
		t.Fatalf("non-post report must not produce signal, got %+v", signals.batches)
	}
}
