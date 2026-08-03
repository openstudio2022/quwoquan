package messaging

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
)

const (
	ViewerRelationshipEventStream   = "events.user.persona_relationship"
	ViewerRelationshipDLQ           = "events.user.persona_relationship.comment.dlq"
	ViewerRelationshipConsumerGroup = "content-comment-viewer-relationship"
)

type viewerRelationshipProjector interface {
	Apply(context.Context, commentapp.ViewerRelationshipEvent) error
}

// ViewerRelationshipConsumer is Comment's typed subscription entrypoint for
// User PersonaRelationship facts. It owns a dedicated consumer group and only
// acknowledges after the object-local projection and inbox are durable.
type ViewerRelationshipConsumer struct {
	redis     rtredis.Client
	projector viewerRelationshipProjector
	consumer  string
	logger    *slog.Logger
}

func NewViewerRelationshipConsumer(
	redis rtredis.Client,
	projector viewerRelationshipProjector,
	consumer string,
	logger *slog.Logger,
) *ViewerRelationshipConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "content-comment-viewer-relationship-worker"
	}
	return &ViewerRelationshipConsumer{
		redis: redis, projector: projector, consumer: consumer, logger: logger,
	}
}

func (consumer *ViewerRelationshipConsumer) EnsureGroup(ctx context.Context) error {
	if consumer == nil || consumer.redis == nil {
		return errors.New("comment viewer relationship Redis is not configured")
	}
	return consumer.redis.XGroupCreateMkStream(
		ctx,
		ViewerRelationshipEventStream,
		ViewerRelationshipConsumerGroup,
		"0",
	)
}

func (consumer *ViewerRelationshipConsumer) ProcessOnce(
	ctx context.Context,
) (int, error) {
	if consumer == nil || consumer.redis == nil || consumer.projector == nil {
		return 0, errors.New("comment viewer relationship consumer is not configured")
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		return 0, err
	}
	messages, err := consumer.redis.XReadGroup(
		ctx,
		ViewerRelationshipConsumerGroup,
		consumer.consumer,
		map[string]string{ViewerRelationshipEventStream: ">"},
		20,
		200*time.Millisecond,
	)
	if err != nil {
		return 0, err
	}
	processed := 0
	for _, message := range messages {
		if err := consumer.processMessage(ctx, message); err != nil {
			if dlqErr := consumer.deadLetter(ctx, message, err); dlqErr != nil {
				return processed, dlqErr
			}
			consumer.logger.ErrorContext(
				ctx,
				"comment viewer relationship event sent to dead letter queue",
				slog.String("streamId", message.ID),
				slog.String("err", err.Error()),
			)
		}
		if err := consumer.redis.XAck(
			ctx,
			ViewerRelationshipEventStream,
			ViewerRelationshipConsumerGroup,
			message.ID,
		); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}

func (consumer *ViewerRelationshipConsumer) Run(
	ctx context.Context,
	interval time.Duration,
) {
	if interval <= 0 {
		interval = 500 * time.Millisecond
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.logger.ErrorContext(
			ctx,
			"comment viewer relationship consumer group unavailable",
			slog.String("err", err.Error()),
		)
		return
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil {
			consumer.logger.ErrorContext(
				ctx,
				"comment viewer relationship consume failed",
				slog.String("err", err.Error()),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *ViewerRelationshipConsumer) processMessage(
	ctx context.Context,
	message rtredis.StreamMessage,
) error {
	event, err := decodeViewerRelationshipEvent(message.Values)
	if err != nil {
		return err
	}
	return consumer.projector.Apply(ctx, event)
}

func (consumer *ViewerRelationshipConsumer) deadLetter(
	ctx context.Context,
	message rtredis.StreamMessage,
	cause error,
) error {
	values := map[string]string{
		"streamId": message.ID,
		"error":    cause.Error(),
	}
	for key, value := range message.Values {
		values[key] = value
	}
	if _, err := consumer.redis.XAdd(ctx, ViewerRelationshipDLQ, values); err != nil {
		return fmt.Errorf("append comment viewer relationship DLQ: %w", err)
	}
	return nil
}

func decodeViewerRelationshipEvent(
	values map[string]string,
) (commentapp.ViewerRelationshipEvent, error) {
	version, err := strconv.ParseInt(strings.TrimSpace(values["version"]), 10, 64)
	if err != nil || version <= 0 {
		return commentapp.ViewerRelationshipEvent{},
			errors.New("invalid persona relationship event version")
	}
	following, err := strconv.ParseBool(strings.TrimSpace(values["following"]))
	if err != nil {
		return commentapp.ViewerRelationshipEvent{},
			errors.New("invalid persona relationship following value")
	}
	occurredAt, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(values["occurredAt"]),
	)
	if err != nil {
		return commentapp.ViewerRelationshipEvent{},
			errors.New("invalid persona relationship occurredAt")
	}
	event := commentapp.ViewerRelationshipEvent{
		EventID:         strings.TrimSpace(values["eventId"]),
		EventName:       commentapp.ViewerRelationshipEventName(strings.TrimSpace(values["eventName"])),
		PairID:          strings.TrimSpace(values["pairId"]),
		SourcePersonaID: strings.TrimSpace(values["sourcePersonaId"]),
		TargetPersonaID: strings.TrimSpace(values["targetPersonaId"]),
		Following:       following,
		Version:         version,
		OccurredAt:      occurredAt.UTC(),
	}
	return event, commentapp.ValidateViewerRelationshipEvent(event)
}
