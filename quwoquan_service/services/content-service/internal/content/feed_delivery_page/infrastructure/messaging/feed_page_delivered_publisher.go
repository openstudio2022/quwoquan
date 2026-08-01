package messaging

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	redisruntime "quwoquan_service/runtime/redis"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
)

const (
	FeedPageDeliveredStream          = "events.content.feed_page_delivered"
	FeedPageDeliveredStreamRetention = 7 * 24 * time.Hour
)

type FeedPageDeliveredPublisher struct {
	transport redisruntime.Client
}

func NewFeedPageDeliveredPublisher(
	transport redisruntime.Client,
) *FeedPageDeliveredPublisher {
	return &FeedPageDeliveredPublisher{transport: transport}
}

func (publisher *FeedPageDeliveredPublisher) Publish(
	ctx context.Context,
	event deliveryapp.FeedPageDelivered,
) error {
	if publisher == nil || publisher.transport == nil {
		return fmt.Errorf("FeedPageDelivered publisher is not configured")
	}
	event = normalizeEvent(event)
	if err := event.Validate(); err != nil {
		return err
	}
	payload, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("encode FeedPageDelivered payload: %w", err)
	}
	digest := sha256.Sum256([]byte("FeedPageDelivered:" + event.DeliveryPageID))
	occurredAt := event.OccurredAt.UTC().Format(time.RFC3339Nano)
	if _, err := publisher.transport.XAdd(
		ctx,
		FeedPageDeliveredStream,
		map[string]string{
			"eventId":        hex.EncodeToString(digest[:]),
			"eventName":      "FeedPageDelivered",
			"deliveryPageId": event.DeliveryPageID,
			"payload":        string(payload),
			"occurredAt":     occurredAt,
		},
	); err != nil {
		return fmt.Errorf("append FeedPageDelivered stream: %w", err)
	}
	if err := publisher.transport.XTrimOlderThan(
		ctx,
		FeedPageDeliveredStream,
		FeedPageDeliveredStreamRetention,
	); err != nil {
		return fmt.Errorf("trim FeedPageDelivered stream: %w", err)
	}
	if err := publisher.transport.Expire(
		ctx,
		FeedPageDeliveredStream,
		FeedPageDeliveredStreamRetention,
	); err != nil {
		return fmt.Errorf("bound inactive FeedPageDelivered stream retention: %w", err)
	}
	return nil
}

func normalizeEvent(event deliveryapp.FeedPageDelivered) deliveryapp.FeedPageDelivered {
	event.DeliveryPageID = strings.TrimSpace(event.DeliveryPageID)
	event.FeedRequestID = strings.TrimSpace(event.FeedRequestID)
	event.SubjectID = strings.TrimSpace(event.SubjectID)
	event.PersonaID = strings.TrimSpace(event.PersonaID)
	event.Scenario = strings.TrimSpace(event.Scenario)
	event.WindowID = strings.TrimSpace(event.WindowID)
	event.ModelBucket = strings.TrimSpace(event.ModelBucket)
	event.RankingSnapshotDigest = strings.TrimSpace(event.RankingSnapshotDigest)
	event.FeatureSnapshotAt = event.FeatureSnapshotAt.UTC()
	event.OccurredAt = event.OccurredAt.UTC()
	if event.ModelChannel != nil {
		value := strings.TrimSpace(*event.ModelChannel)
		event.ModelChannel = &value
	}
	if event.ModelReleaseID != nil {
		value := strings.TrimSpace(*event.ModelReleaseID)
		event.ModelReleaseID = &value
	}
	event.UserFeatureSnapshot = cloneMap(event.UserFeatureSnapshot)
	items := make([]deliveryapp.DeliveredRecommendationItem, len(event.Items))
	for index, item := range event.Items {
		item.ContentID = strings.TrimSpace(item.ContentID)
		item.ContentType = strings.TrimSpace(item.ContentType)
		item.FeatureSnapshotDigest = strings.TrimSpace(item.FeatureSnapshotDigest)
		item.ItemFeatureSnapshot = cloneMap(item.ItemFeatureSnapshot)
		items[index] = item
	}
	event.Items = items
	return event
}

func cloneMap(source map[string]any) map[string]any {
	if source == nil {
		return nil
	}
	clone := make(map[string]any, len(source))
	for key, value := range source {
		clone[key] = value
	}
	return clone
}

var _ deliveryapp.FeedPageDeliveredPublisher = (*FeedPageDeliveredPublisher)(nil)
