package tagfeedbackstore

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	feedbackmodel "quwoquan_service/services/tag-service/internal/tag/tag_feedback/domain/tagfeedback/model"
)

const (
	FeedbackEventStream = "events.tag.feedback"
	feedbackEventTTL    = 7 * 24 * time.Hour
)

type feedbackEventTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

type FeedbackEventPublisher interface {
	PublishTagFeedbackRecorded(
		ctx context.Context,
		feedback feedbackmodel.Feedback,
	) error
}

// StreamEventPublisher projects committed TagFeedback facts onto the
// metadata-owned durable stream. The stable feedback ID is also the event ID,
// so downstream consumers can converge at-least-once retries.
type StreamEventPublisher struct {
	transport feedbackEventTransport
}

func NewStreamEventPublisher(
	transport feedbackEventTransport,
) (*StreamEventPublisher, error) {
	if transport == nil {
		return nil, fmt.Errorf(
			"tag feedback event publisher requires message transport",
		)
	}
	return &StreamEventPublisher{transport: transport}, nil
}

func (publisher *StreamEventPublisher) PublishTagFeedbackRecorded(
	ctx context.Context,
	feedback feedbackmodel.Feedback,
) error {
	if publisher == nil || publisher.transport == nil {
		return fmt.Errorf("tag feedback event publisher is not configured")
	}
	values, err := feedbackEventValues(feedback)
	if err != nil {
		return err
	}
	if _, err := publisher.transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: FeedbackEventStream,
			Fields: sortedDurableFields(values),
		},
	); err != nil {
		return fmt.Errorf("append TagFeedbackRecorded event: %w", err)
	}
	if err := publisher.transport.SetDurableRetention(
		ctx,
		FeedbackEventStream,
		feedbackEventTTL,
	); err != nil {
		return fmt.Errorf("trim tag feedback event stream: %w", err)
	}
	return nil
}

func feedbackEventValues(
	feedback feedbackmodel.Feedback,
) (map[string]string, error) {
	if strings.TrimSpace(feedback.ID) == "" ||
		strings.TrimSpace(feedback.ActorID) == "" ||
		strings.TrimSpace(feedback.ActorKind) == "" ||
		strings.TrimSpace(feedback.TagRef) == "" ||
		strings.TrimSpace(feedback.Action) == "" ||
		feedback.RecordedAt.IsZero() {
		return nil, fmt.Errorf("TagFeedbackRecorded payload is incomplete")
	}
	return map[string]string{
		"eventName":  "TagFeedbackRecorded",
		"eventId":    strings.TrimSpace(feedback.ID),
		"id":         strings.TrimSpace(feedback.ID),
		"actorId":    strings.TrimSpace(feedback.ActorID),
		"actorKind":  strings.TrimSpace(feedback.ActorKind),
		"tagRef":     strings.TrimSpace(feedback.TagRef),
		"action":     strings.TrimSpace(feedback.Action),
		"recordedAt": feedback.RecordedAt.UTC().Format(time.RFC3339Nano),
	}, nil
}

func sortedDurableFields(
	values map[string]string,
) []runtimemessaging.DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, runtimemessaging.DurableField{
			Name:  key,
			Value: values[key],
		})
	}
	return fields
}

var _ FeedbackEventPublisher = (*StreamEventPublisher)(nil)
