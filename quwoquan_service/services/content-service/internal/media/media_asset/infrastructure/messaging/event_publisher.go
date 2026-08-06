package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

const (
	MediaAssetEventStream          = "events.content.media_assets"
	MediaAssetEventStreamRetention = 7 * 24 * time.Hour
)

type EventPublisher struct {
	transport runtimemessaging.DurableRecordAppender
}

func NewEventPublisher(
	transport runtimemessaging.DurableRecordAppender,
) (*EventPublisher, error) {
	if transport == nil {
		return nil, fmt.Errorf("MediaAsset durable transport is required")
	}
	return &EventPublisher{transport: transport}, nil
}

func (publisher *EventPublisher) Publish(
	ctx context.Context,
	event mediaports.OutboxEvent,
) error {
	if publisher == nil || publisher.transport == nil {
		return fmt.Errorf("MediaAsset event publisher is not configured")
	}
	if event.AggregateType != "MediaAsset" ||
		strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" ||
		event.AggregateVersion <= 0 || event.OccurredAt.IsZero() ||
		!json.Valid(event.Payload) {
		return fmt.Errorf("MediaAsset event identity or payload is invalid")
	}
	eventType, payload, err := canonicalMediaAssetPublication(event)
	if err != nil {
		return err
	}
	if err := runtimemessaging.AppendDurableRecord(
		ctx,
		publisher.transport,
		MediaAssetEventStream,
		map[string]string{
			"eventId":          event.EventID,
			"eventType":        eventType,
			"aggregateType":    event.AggregateType,
			"aggregateId":      event.AggregateID,
			"aggregateVersion": strconv.FormatInt(event.AggregateVersion, 10),
			"payload":          string(payload),
			"occurredAt":       event.OccurredAt.UTC().Format(time.RFC3339Nano),
			"checkpoint":       event.Checkpoint,
		},
		MediaAssetEventStreamRetention,
	); err != nil {
		return fmt.Errorf("append MediaAsset event stream: %w", err)
	}
	return nil
}

func canonicalMediaAssetPublication(event mediaports.OutboxEvent) (string, []byte, error) {
	var source map[string]json.RawMessage
	if err := json.Unmarshal(event.Payload, &source); err != nil {
		return "", nil, fmt.Errorf("decode MediaAsset event payload: %w", err)
	}
	canonical := map[string]any{
		"id":      event.AggregateID,
		"version": event.AggregateVersion,
	}
	copyRequired := func(names ...string) error {
		for _, name := range names {
			value, found := source[name]
			if !found || len(value) == 0 || string(value) == "null" {
				return fmt.Errorf("MediaAsset %s payload is missing %s", event.EventType, name)
			}
			canonical[name] = value
		}
		return nil
	}
	var (
		eventType string
		err       error
	)
	switch event.EventType {
	case "content.media_asset.created", "MediaAssetCreated":
		eventType = "MediaAssetCreated"
		err = copyRequired("ownerId", "sourceSessionId", "objectKey", "sha256", "processingStatus")
	case "content.media_asset.processing_updated", "MediaAssetProcessingUpdated":
		eventType = "MediaAssetProcessingUpdated"
		err = copyRequired("processingStatus")
		canonical["processedAt"] = event.OccurredAt.UTC()
	case "content.media_asset.access_policy_updated", "MediaAssetAccessPolicyUpdated":
		eventType = "MediaAssetAccessPolicyUpdated"
		err = copyRequired("ownerId", "accessPolicy")
	case "content.media_asset.discarded", "MediaAssetDiscarded":
		eventType = "MediaAssetDiscarded"
		err = copyRequired("ownerId", "objectKey", "processingStatus")
	default:
		return "", nil, fmt.Errorf("MediaAsset event type %q is not canonical", event.EventType)
	}
	if err != nil {
		return "", nil, err
	}
	encoded, err := json.Marshal(canonical)
	if err != nil {
		return "", nil, fmt.Errorf("encode MediaAsset canonical payload: %w", err)
	}
	return eventType, encoded, nil
}

var _ mediaports.OutboxPublisher = (*EventPublisher)(nil)
