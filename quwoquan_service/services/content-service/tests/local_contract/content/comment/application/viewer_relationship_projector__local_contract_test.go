package comment_test

import (
	"context"
	"testing"
	"time"

	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
)

func TestCommentViewerRelationshipProjectorOwnsOrderingAndBlockSemantics(
	t *testing.T,
) {
	writer := newViewerRelationshipWriter()
	projector := commentapp.NewViewerRelationshipProjector(writer)
	now := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)

	applyViewerRelationshipEvent(t, projector, commentapp.ViewerRelationshipEvent{
		EventID: "follow", EventName: commentapp.ViewerFollowStateChanged,
		PairID: "pair", SourcePersonaID: "viewer", TargetPersonaID: "author",
		Following: true, Version: 2, OccurredAt: now,
	})
	applyViewerRelationshipEvent(t, projector, commentapp.ViewerRelationshipEvent{
		EventID: "stale", EventName: commentapp.ViewerFollowStateChanged,
		PairID: "pair", SourcePersonaID: "viewer", TargetPersonaID: "author",
		Following: false, Version: 1, OccurredAt: now.Add(time.Second),
	})
	if got := writer.direction("viewer", "author"); !got.following || got.version != 2 {
		t.Fatalf("stale event overwrote newer Comment relation: %+v", got)
	}
	applyViewerRelationshipEvent(t, projector, commentapp.ViewerRelationshipEvent{
		EventID: "reciprocal", EventName: commentapp.ViewerFollowStateChanged,
		PairID: "pair", SourcePersonaID: "author", TargetPersonaID: "viewer",
		Following: true, Version: 3, OccurredAt: now.Add(2 * time.Second),
	})
	applyViewerRelationshipEvent(t, projector, commentapp.ViewerRelationshipEvent{
		EventID: "block", EventName: commentapp.ViewerBlocked,
		PairID: "pair", SourcePersonaID: "viewer", TargetPersonaID: "author",
		Version: 4, OccurredAt: now.Add(3 * time.Second),
	})
	if writer.direction("viewer", "author").following ||
		writer.direction("author", "viewer").following {
		t.Fatal("PersonaBlocked must clear both Comment follow directions")
	}
	if !writer.blocked["viewer|author"] {
		t.Fatal("PersonaBlocked did not project Comment block state")
	}
	applyViewerRelationshipEvent(t, projector, commentapp.ViewerRelationshipEvent{
		EventID: "unblock", EventName: commentapp.ViewerUnblocked,
		PairID: "pair", SourcePersonaID: "viewer", TargetPersonaID: "author",
		Version: 5, OccurredAt: now.Add(4 * time.Second),
	})
	if writer.blocked["viewer|author"] {
		t.Fatal("PersonaUnblocked did not clear Comment block state")
	}
	if writer.direction("viewer", "author").following {
		t.Fatal("unblock must not restore an earlier follow state")
	}
}

func applyViewerRelationshipEvent(
	t *testing.T,
	projector *commentapp.ViewerRelationshipProjector,
	event commentapp.ViewerRelationshipEvent,
) {
	t.Helper()
	if err := projector.Apply(context.Background(), event); err != nil {
		t.Fatalf("apply viewer relationship event %s: %v", event.EventID, err)
	}
}

type viewerRelationshipDirection struct {
	following bool
	version   int64
}

type viewerRelationshipWriter struct {
	directions map[string]viewerRelationshipDirection
	blocked    map[string]bool
	events     map[string]struct{}
}

func newViewerRelationshipWriter() *viewerRelationshipWriter {
	return &viewerRelationshipWriter{
		directions: map[string]viewerRelationshipDirection{},
		blocked:    map[string]bool{}, events: map[string]struct{}{},
	}
}

func (writer *viewerRelationshipWriter) ApplyFollowState(
	_ context.Context,
	event commentapp.ViewerRelationshipEvent,
) error {
	key := event.SourcePersonaID + "|" + event.TargetPersonaID
	if current, exists := writer.directions[key]; exists && current.version >= event.Version {
		return nil
	}
	writer.directions[key] = viewerRelationshipDirection{
		following: event.Following,
		version:   event.Version,
	}
	return nil
}

func (writer *viewerRelationshipWriter) ApplyBlockState(
	_ context.Context,
	event commentapp.ViewerRelationshipEvent,
	blocked bool,
) error {
	writer.blocked[event.SourcePersonaID+"|"+event.TargetPersonaID] = blocked
	return nil
}

func (writer *viewerRelationshipWriter) RecordAppliedEvent(
	_ context.Context,
	event commentapp.ViewerRelationshipEvent,
) (bool, error) {
	if _, exists := writer.events[event.EventID]; exists {
		return false, nil
	}
	writer.events[event.EventID] = struct{}{}
	return true, nil
}

func (writer *viewerRelationshipWriter) direction(
	source string,
	target string,
) viewerRelationshipDirection {
	return writer.directions[source+"|"+target]
}
