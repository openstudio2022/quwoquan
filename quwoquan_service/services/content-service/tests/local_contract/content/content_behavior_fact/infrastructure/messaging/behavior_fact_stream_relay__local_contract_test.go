package messaging_test

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	behaviorstream "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/messaging"
)

func TestBuildStreamValuesUsesDeterministicFactIdentity(t *testing.T) {
	t.Parallel()
	row := behaviorstream.BehaviorFactDocument{
		ID:            bson.NewObjectID(),
		ClientEventID: "client-event-001",
		UserID:        "persona-001",
		SessionID:     "session-001",
		ContentID:     "post-001",
		ContentType:   "post",
		Action:        "like",
		FeedRequestID: "feed-request-001",
		OccurredAt:    "2026-07-31T08:00:00Z",
		CreatedAt:     time.Date(2026, 7, 31, 8, 0, 0, 0, time.UTC),
	}
	values, err := behaviorstream.BuildStreamValues(row)
	if err != nil {
		t.Fatalf("build behavior stream values: %v", err)
	}
	expected := sha256.Sum256([]byte("ContentBehaviorRecorded:persona-001:client-event-001"))
	if values["eventId"] != hex.EncodeToString(expected[:]) {
		t.Fatalf("unexpected eventId: %s", values["eventId"])
	}
	if values["sourceSequence"] != row.ID.Hex() || values["subjectId"] != row.UserID {
		t.Fatalf("source coordinate mismatch: %+v", values)
	}
	var payload map[string]any
	if err := json.Unmarshal([]byte(values["payload"]), &payload); err != nil {
		t.Fatalf("decode payload: %v", err)
	}
	if payload["clientEventId"] != row.ClientEventID || payload["contentId"] != row.ContentID {
		t.Fatalf("payload mismatch: %+v", payload)
	}
}

func TestBuildStreamValuesRejectsIncompleteIdentity(t *testing.T) {
	t.Parallel()
	_, err := behaviorstream.BuildStreamValues(behaviorstream.BehaviorFactDocument{
		ID:         bson.NewObjectID(),
		UserID:     "persona-001",
		Action:     "like",
		OccurredAt: "2026-07-31T08:00:00Z",
	})
	if err == nil {
		t.Fatal("expected missing clientEventId to fail")
	}
}
