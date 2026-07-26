package api_integration

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	feedbackmodel "quwoquan_service/services/tag-service/internal/tag/tag_feedback/domain/tagfeedback/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback/infrastructure/tagfeedbackstore"
)

type retryingTagFeedbackPublisher struct {
	mu       sync.Mutex
	failures int
	eventIDs []string
}

func (publisher *retryingTagFeedbackPublisher) PublishTagFeedbackRecorded(
	_ context.Context,
	feedback feedbackmodel.Feedback,
) error {
	publisher.mu.Lock()
	defer publisher.mu.Unlock()
	publisher.eventIDs = append(publisher.eventIDs, feedback.ID)
	if publisher.failures > 0 {
		publisher.failures--
		return errors.New("temporary stream outage")
	}
	return nil
}

func TestTagFeedbackEventRelayRecoversCommittedFact(t *testing.T) {
	cleanCollections(t)
	sink := tagfeedbackstore.NewSink(mongoDB)
	if err := sink.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	fact, err := feedbackmodel.NewFeedback(
		"feedback-event-1",
		"persona-event-1",
		"persona",
		"Topic/旅行",
		"click",
		"search_suggestion",
		"idem-event-1",
		time.Now().UTC(),
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, replayed, err := sink.Append(t.Context(), fact); err != nil || replayed {
		t.Fatalf("append fact replayed=%v err=%v", replayed, err)
	}

	publisher := &retryingTagFeedbackPublisher{failures: 1}
	relay, err := tagfeedbackstore.NewEventRelay(sink, publisher, nil)
	if err != nil {
		t.Fatal(err)
	}
	if didWork, err := relay.ProcessOnce(t.Context()); !didWork || err == nil {
		t.Fatalf("first relay didWork=%v err=%v", didWork, err)
	}
	pending, err := mongoDB.Collection("tag_feedback").CountDocuments(
		t.Context(),
		bson.M{
			"_id":              fact.ID,
			"eventPublishedAt": bson.M{"$exists": false},
		},
	)
	if err != nil || pending != 1 {
		t.Fatalf("pending after failure=%d err=%v", pending, err)
	}

	if didWork, err := relay.ProcessOnce(t.Context()); !didWork || err != nil {
		t.Fatalf("retry relay didWork=%v err=%v", didWork, err)
	}
	if didWork, err := relay.ProcessOnce(t.Context()); didWork || err != nil {
		t.Fatalf("drained relay didWork=%v err=%v", didWork, err)
	}
	publisher.mu.Lock()
	eventIDs := append([]string(nil), publisher.eventIDs...)
	publisher.mu.Unlock()
	if len(eventIDs) != 2 ||
		eventIDs[0] != fact.ID ||
		eventIDs[1] != fact.ID {
		t.Fatalf("stable event retries = %#v", eventIDs)
	}
	published, err := mongoDB.Collection("tag_feedback").CountDocuments(
		t.Context(),
		bson.M{
			"_id":              fact.ID,
			"eventPublishedAt": bson.M{"$exists": true},
		},
	)
	if err != nil || published != 1 {
		t.Fatalf("published acknowledgement=%d err=%v", published, err)
	}
}
