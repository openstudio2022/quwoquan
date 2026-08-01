package tag_feedback_fact_test

import (
	"context"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	feedbackmodel "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/domain/tagfeedback/model"
	tagfeedbackstore "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/infrastructure/tagfeedbackstore"
)

func TestStreamEventPublisherUsesMetadataStreamAndStableEventID(t *testing.T) {
	client := rtredis.NewMemoryClient()
	transport, err := runtimemessaging.NewRedisMessageTransport(
		client,
		client,
	)
	if err != nil {
		t.Fatal(err)
	}
	publisher, err := tagfeedbackstore.NewStreamEventPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	feedback, err := feedbackmodel.NewFeedback(
		"feedback-stable-1",
		"persona-1",
		"persona",
		"Topic/旅行",
		"click",
		"search_suggestion",
		"idem-1",
		time.Date(2026, 7, 26, 8, 0, 0, 0, time.UTC),
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := publisher.PublishTagFeedbackRecorded(
		context.Background(),
		feedback,
	); err != nil {
		t.Fatal(err)
	}
	if err := transport.EnsureDurableConsumerGroup(
		context.Background(),
		tagfeedbackstore.FeedbackEventStream,
		"tag-feedback-test",
		"0",
	); err != nil {
		t.Fatal(err)
	}
	deliveries, err := transport.ReadDurable(
		context.Background(),
		runtimemessaging.StreamReadRequest{
			Stream:   tagfeedbackstore.FeedbackEventStream,
			Group:    "tag-feedback-test",
			Consumer: "reader-1",
			Count:    1,
			Block:    time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(deliveries) != 1 {
		t.Fatalf("deliveries=%d", len(deliveries))
	}
	fields := map[string]string{}
	for _, field := range deliveries[0].Fields {
		fields[field.Name] = field.Value
	}
	if fields["eventName"] != "TagFeedbackRecorded" ||
		fields["eventId"] != feedback.ID ||
		fields["id"] != feedback.ID ||
		fields["actorId"] != feedback.ActorID ||
		fields["tagRef"] != feedback.TagRef {
		t.Fatalf("stream fields = %#v", fields)
	}
}
