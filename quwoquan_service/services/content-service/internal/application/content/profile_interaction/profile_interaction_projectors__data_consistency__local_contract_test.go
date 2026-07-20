package profileinteraction

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	activitymodel "quwoquan_service/services/content-service/internal/domain/content/profile_interaction_activity_view/model"
	activityports "quwoquan_service/services/content-service/internal/domain/content/profile_interaction_activity_view/ports"
	readfactmodel "quwoquan_service/services/content-service/internal/domain/content/profile_interaction_read_fact/model"
	readfactports "quwoquan_service/services/content-service/internal/domain/content/profile_interaction_read_fact/ports"
	reactionports "quwoquan_service/services/content-service/internal/domain/reaction/ports"
)

func TestProfileInteractionProjectionFailureDoesNotAdvanceCheckpoint(t *testing.T) {
	now := time.Date(2026, time.July, 20, 1, 0, 0, 0, time.UTC)
	payload, err := json.Marshal(reactionFact{
		ReactionID:     "reaction-profile-projection",
		Version:        1,
		TargetKind:     "post",
		TargetID:       "post-profile-projection",
		TargetAuthorID: "profile-owner",
		ActorDimension: "persona",
		ActorID:        "profile-actor",
		Reaction:       "like",
		OccurredAt:     now,
		IdempotencyKey: "profile-projection",
	})
	if err != nil {
		t.Fatal(err)
	}
	outbox := &reactionRelayStore{events: []reactionports.OutboxFact{{
		EventID:          "reaction:reaction-profile-projection:1",
		EventType:        reactionapp.EventTypeContentReactionSet,
		AggregateID:      "reaction-profile-projection",
		AggregateVersion: 1,
		Payload:          payload,
		OccurredAt:       now,
		Checkpoint:       "1",
	}}}
	writer := newMemoryActivityWriter()
	writer.failUpsert = true
	projector := NewProjector(
		staticProjectionSource{post: activityports.PostSlice{
			ID: "post-profile-projection", Version: 1,
			AuthorPersonaID: "profile-owner", ContentType: "image",
			Title: "projection target", Status: "published", Visibility: "public",
		}},
		writer,
	)
	relay := reactionapp.NewOutboxRelay(
		outbox,
		outbox,
		NewReactionProjector(projector),
		"profile-interaction-local-contract",
	)

	if _, err := relay.Drain(context.Background(), 10); err == nil {
		t.Fatal("projection failure must be returned")
	}
	if outbox.checkpoint != "" {
		t.Fatalf("failed projection advanced checkpoint to %q", outbox.checkpoint)
	}
	if len(writer.rows) != 0 {
		t.Fatalf("failed projection wrote rows: %+v", writer.rows)
	}

	writer.failUpsert = false
	if count, err := relay.Drain(context.Background(), 10); err != nil || count != 1 {
		t.Fatalf("projection retry count=%d err=%v", count, err)
	}
	if outbox.checkpoint != "1" {
		t.Fatalf("successful projection checkpoint=%q", outbox.checkpoint)
	}
	if len(writer.rows) != 2 {
		t.Fatalf("received/sent projection rows=%d, want 2", len(writer.rows))
	}
}

func TestProfileInteractionReadFactProjectionFailureKeepsCheckpoint(t *testing.T) {
	now := time.Date(2026, time.July, 20, 2, 0, 0, 0, time.UTC)
	fact, err := readfactmodel.New("read-owner", "read-activity", "read", now)
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(fact)
	if err != nil {
		t.Fatal(err)
	}
	outbox := &readFactRelayStore{events: []readfactports.OutboxEvent{{
		EventID:    fact.FactID,
		EventType:  ProfileInteractionReadFactAppended,
		Payload:    payload,
		OccurredAt: now,
		Checkpoint: "7",
	}}}
	writer := newMemoryActivityWriter()
	writer.failReadState = true
	relay := NewReadFactOutboxRelay(
		outbox,
		outbox,
		NewReadFactProjector(writer),
		"profile-interaction-read-local-contract",
	)

	if _, err := relay.Drain(context.Background(), 10); err == nil {
		t.Fatal("read projection failure must be returned")
	}
	if outbox.checkpoint != "" {
		t.Fatalf("failed read projection advanced checkpoint to %q", outbox.checkpoint)
	}

	writer.failReadState = false
	if count, err := relay.Drain(context.Background(), 10); err != nil || count != 1 {
		t.Fatalf("read projection retry count=%d err=%v", count, err)
	}
	if outbox.checkpoint != "7" || writer.readStateCalls != 1 {
		t.Fatalf(
			"read projection checkpoint=%q calls=%d",
			outbox.checkpoint,
			writer.readStateCalls,
		)
	}
}

type staticProjectionSource struct {
	post activityports.PostSlice
}

func (s staticProjectionSource) FindPost(
	_ context.Context,
	postID string,
) (activityports.PostSlice, bool, error) {
	if s.post.ID != postID {
		return activityports.PostSlice{}, false, nil
	}
	return s.post, true, nil
}

func (staticProjectionSource) FindComment(
	context.Context,
	string,
) (activityports.CommentSlice, bool, error) {
	return activityports.CommentSlice{}, false, nil
}

type memoryActivityWriter struct {
	rows           map[string]activitymodel.Activity
	failUpsert     bool
	failReadState  bool
	readStateCalls int
}

func newMemoryActivityWriter() *memoryActivityWriter {
	return &memoryActivityWriter{rows: map[string]activitymodel.Activity{}}
}

func (w *memoryActivityWriter) Upsert(
	_ context.Context,
	activity activitymodel.Activity,
) error {
	if w.failUpsert {
		return errors.New("injected projection failure")
	}
	key := activity.OwnerPersonaID + "/" + activity.Direction + "/" + activity.ActivityID
	if existing, found := w.rows[key]; !found ||
		activity.SourceVersion > existing.SourceVersion {
		w.rows[key] = activity
	}
	return nil
}

func (*memoryActivityWriter) DeactivateActivity(context.Context, string, int64) error {
	return nil
}

func (*memoryActivityWriter) SetCommentViewerReaction(
	context.Context,
	string,
	string,
	string,
	int64,
) error {
	return nil
}

func (*memoryActivityWriter) MarkTargetUnavailable(
	context.Context,
	string,
	int64,
	time.Time,
) error {
	return nil
}

func (w *memoryActivityWriter) ApplyReadState(
	context.Context,
	string,
	string,
	string,
	time.Time,
) error {
	if w.failReadState {
		return errors.New("injected read projection failure")
	}
	w.readStateCalls++
	return nil
}

type reactionRelayStore struct {
	events     []reactionports.OutboxFact
	checkpoint string
}

func (s *reactionRelayStore) ReadAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]reactionports.OutboxFact, error) {
	if checkpoint == "1" {
		return nil, nil
	}
	return append([]reactionports.OutboxFact(nil), s.events...), nil
}

func (s *reactionRelayStore) LoadCheckpoint(context.Context, string) (string, error) {
	return s.checkpoint, nil
}

func (s *reactionRelayStore) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	s.checkpoint = checkpoint
	return nil
}

type readFactRelayStore struct {
	events     []readfactports.OutboxEvent
	checkpoint string
}

func (s *readFactRelayStore) ReadAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]readfactports.OutboxEvent, error) {
	if checkpoint == "7" {
		return nil, nil
	}
	return append([]readfactports.OutboxEvent(nil), s.events...), nil
}

func (s *readFactRelayStore) LoadCheckpoint(context.Context, string) (string, error) {
	return s.checkpoint, nil
}

func (s *readFactRelayStore) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	s.checkpoint = checkpoint
	return nil
}
