package messaging_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"testing"
	"time"

	redisruntime "quwoquan_service/runtime/redis"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymessaging "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/messaging"
)

func TestFeedPageDeliveredPublisherEmitsCanonicalEnvelope(t *testing.T) {
	client := redisruntime.NewMemoryClient()
	publisher := deliverymessaging.NewFeedPageDeliveredPublisher(client)
	now := time.Now().UTC().Truncate(time.Microsecond)
	event := deliveryapp.FeedPageDelivered{
		DeliveryPageID:        "fdp-delivered-1",
		FeedRequestID:         "frq-delivered-1",
		SubjectID:             "subject-1",
		PersonaID:             "persona-1",
		Scenario:              "content_feed",
		WindowID:              "window-1",
		ModelBucket:           "rule",
		RankingSnapshotDigest: "ranking-digest",
		FeatureSnapshotAt:     now.Add(-time.Second),
		UserFeatureSnapshot:   map[string]any{"interest": 1.0},
		Items: []deliveryapp.DeliveredRecommendationItem{{
			Ordinal:               3,
			ContentID:             "post-1",
			ContentType:           "photo",
			FeatureSnapshotDigest: "feature-digest",
			ItemFeatureSnapshot:   map[string]any{"qualityScore": 1.0},
		}},
		OccurredAt: now,
	}
	if err := publisher.Publish(context.Background(), event); err != nil {
		t.Fatalf("publish: %v", err)
	}
	messages, err := client.XRead(
		context.Background(),
		map[string]string{deliverymessaging.FeedPageDeliveredStream: "0-0"},
		10,
		0,
	)
	if err != nil || len(messages) != 1 {
		t.Fatalf("messages=%v err=%v", messages, err)
	}
	values := messages[0].Values
	digest := sha256.Sum256([]byte("FeedPageDelivered:" + event.DeliveryPageID))
	if values["eventId"] != hex.EncodeToString(digest[:]) ||
		values["eventName"] != "FeedPageDelivered" ||
		values["deliveryPageId"] != event.DeliveryPageID {
		t.Fatalf("envelope=%v", values)
	}
	var payload deliveryapp.FeedPageDelivered
	if err := json.Unmarshal([]byte(values["payload"]), &payload); err != nil {
		t.Fatalf("decode payload: %v", err)
	}
	if payload.Items[0].ContentID != "post-1" || payload.OccurredAt != now {
		t.Fatalf("payload=%+v", payload)
	}
}
