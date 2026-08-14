package userprofile

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

type recordingProjectionWriter struct {
	events []es.ChangeEvent
}

func (writer *recordingProjectionWriter) Apply(
	_ context.Context,
	event es.ChangeEvent,
) error {
	writer.events = append(writer.events, event)
	return nil
}

func TestApplyProviderProjectionReplaysStableUserDocument(t *testing.T) {
	writer := &recordingProjectionWriter{}
	projection := &MongoUserProfileSearchProjection{writer: writer}
	event := application.UserProfileSearchProjectionEvent{
		EventID:        "ups_reconcile",
		UserID:         "user-1",
		ProfileVersion: 7,
		Operation:      "upsert",
		Nickname:       "都江堰作者",
		IdentityTags:   []string{},
		UpdatedAt:      time.Date(2026, 8, 14, 0, 0, 0, 0, time.UTC),
	}

	if err := projection.applyProviderProjection(t.Context(), event); err != nil {
		t.Fatal(err)
	}
	if len(writer.events) != 1 ||
		writer.events[0].Doc.ObjectID != event.UserID ||
		writer.events[0].Op != es.OpUpsert {
		t.Fatalf("provider replay=%+v", writer.events)
	}
}
