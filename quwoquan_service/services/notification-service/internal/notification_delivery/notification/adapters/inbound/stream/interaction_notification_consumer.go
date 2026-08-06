// Package stream 承载 notification-service 的 durable 事件消费 adapter。
// 互动事件经 Redis Stream consumer group at-least-once 投递，投影为
// AppMessage；幂等由 CreateAppMessage 的 idempotencyKey 唯一索引收敛。
package stream

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

const (
	interactionConsumerGroup            = "notification-service"
	interactionDLQSuffix                = ".notification-dlq"
	interactionMaxAttempts        int64 = 5
	interactionDLQRetention             = 7 * 24 * time.Hour
	interactionDefaultBatch       int64 = 50
	interactionDefaultMinIdleTime       = 30 * time.Second
)

// InteractionFailureStore 为每条 stream 消息保存独立失败计数与终态标记。
// source PEL 只有成功或受控恢复后才能 ACK。
type InteractionFailureStore interface {
	RecordInteractionFailure(
		ctx context.Context,
		stream string,
		messageID string,
		eventID string,
		errorClass string,
		cause error,
	) (int64, error)
	IsInteractionDeadLettered(
		ctx context.Context,
		stream string,
		messageID string,
	) (bool, error)
	MarkInteractionDeadLettered(
		ctx context.Context,
		stream string,
		messageID string,
	) error
	ClearInteractionFailure(ctx context.Context, stream string, messageID string) error
}

type DurableMessageTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

type GatheringInvitationEventHandler interface {
	Handle(context.Context, application.InteractionStreamEvent) error
}

type InteractionNotificationConsumer struct {
	transport            DurableMessageTransport
	facade               *application.AppMessageCommandFacade
	gatheringInvitations GatheringInvitationEventHandler
	failures             InteractionFailureStore
	consumer             string
	streams              []string
	minIdle              time.Duration
	logger               *slog.Logger
	mu                   sync.RWMutex
	lastSuccess          time.Time
	lastFailure          error
}

func NewInteractionNotificationConsumer(
	transport DurableMessageTransport,
	facade *application.AppMessageCommandFacade,
	failures InteractionFailureStore,
	consumer string,
	logger *slog.Logger,
	gatheringInvitations ...GatheringInvitationEventHandler,
) (*InteractionNotificationConsumer, error) {
	if transport == nil || facade == nil || failures == nil {
		return nil, fmt.Errorf(
			"interaction notification consumer requires message transport, app message facade, and failure store",
		)
	}
	if logger == nil {
		logger = slog.Default()
	}
	if len(gatheringInvitations) > 1 {
		return nil, fmt.Errorf("only one Gathering invitation handler is allowed")
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "notification-interaction-projector"
	}
	result := &InteractionNotificationConsumer{
		transport: transport,
		facade:    facade,
		failures:  failures,
		consumer:  consumer,
		streams:   append([]string(nil), application.InteractionNotificationStreams...),
		minIdle:   interactionDefaultMinIdleTime,
		logger:    logger,
	}
	if len(gatheringInvitations) == 1 {
		result.gatheringInvitations = gatheringInvitations[0]
	}
	return result, nil
}

func (c *InteractionNotificationConsumer) EnsureGroups(ctx context.Context) error {
	for _, stream := range c.streams {
		if err := c.transport.EnsureDurableConsumerGroup(
			ctx,
			stream,
			interactionConsumerGroup,
			"0",
		); err != nil {
			return fmt.Errorf("ensure consumer group for %s: %w", stream, err)
		}
	}
	return nil
}

func (c *InteractionNotificationConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if err := c.EnsureGroups(ctx); err != nil {
		c.recordFailure(err)
		return 0, err
	}
	processed := 0
	var firstErr error
	for _, stream := range c.streams {
		count, err := c.processStream(ctx, stream)
		processed += count
		if err != nil && firstErr == nil {
			firstErr = err
		}
	}
	if firstErr != nil {
		c.recordFailure(firstErr)
		return processed, firstErr
	}
	c.recordSuccess()
	return processed, nil
}

func (c *InteractionNotificationConsumer) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 250 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := c.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			c.logger.ErrorContext(ctx, "interaction notification consume failed",
				slog.String("errorDigest", irreversibleStreamDigest(err.Error())))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *InteractionNotificationConsumer) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.lastSuccess.IsZero() {
		return fmt.Errorf("interaction notification consumer has not completed a scan")
	}
	if c.lastFailure != nil {
		return fmt.Errorf("interaction notification consumer last failure: %w", c.lastFailure)
	}
	if time.Since(c.lastSuccess) > maxStaleness {
		return fmt.Errorf("interaction notification consumer heartbeat is stale")
	}
	return nil
}

func (c *InteractionNotificationConsumer) processStream(
	ctx context.Context,
	stream string,
) (int, error) {
	claimed, _, err := c.transport.ReclaimDurable(
		ctx, stream, interactionConsumerGroup, c.consumer, c.minIdle, "0-0",
		interactionDefaultBatch,
	)
	if err != nil {
		return 0, fmt.Errorf("auto-claim %s: %w", stream, err)
	}
	fresh, err := c.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   stream,
			Group:    interactionConsumerGroup,
			Consumer: c.consumer,
			Count:    interactionDefaultBatch,
			Block:    100 * time.Millisecond,
		},
	)
	if err != nil {
		return 0, fmt.Errorf("read %s: %w", stream, err)
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueStreamMessages(claimed, fresh) {
		if err := c.processMessage(ctx, stream, message); err != nil {
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		processed++
	}
	return processed, firstErr
}

func (c *InteractionNotificationConsumer) processMessage(
	ctx context.Context,
	stream string,
	message runtimemessaging.StreamDelivery,
) error {
	deadLettered, stateErr := c.failures.IsInteractionDeadLettered(
		ctx,
		stream,
		message.ID,
	)
	if stateErr != nil {
		return fmt.Errorf(
			"read interaction dead-letter state on %s: %w",
			stream,
			stateErr,
		)
	}
	if deadLettered {
		// 原始消息仍留在 source PEL；受控恢复只会清除这个终态标记，
		// 下一轮读取再使用 source stream 的原始 payload。
		return nil
	}
	event, err := normalizeInteractionMessage(stream, message)
	errorClass := "invalid_event"
	if err == nil {
		errorClass = "projection_failed"
		if event.EventType == "GatheringInvitationChanged" ||
			event.EventType == "GatheringCancelled" {
			if c.gatheringInvitations == nil {
				err = fmt.Errorf("Gathering invitation projection is not configured")
			} else {
				err = c.gatheringInvitations.Handle(ctx, event)
			}
		} else {
			var commands []*application.CreateAppMessageCommand
			commands, err = (application.InteractionNotificationProjection{}).Project(event)
			for _, command := range commands {
				if err != nil {
					break
				}
				if command == nil {
					continue
				}
				_, err = c.facade.Create(ctx, *command)
			}
		}
	}
	if err != nil {
		attempts, recordErr := c.failures.RecordInteractionFailure(
			ctx,
			stream,
			message.ID,
			durableFieldValue(message.Fields, "eventId"),
			errorClass,
			err,
		)
		if recordErr != nil {
			return fmt.Errorf("record interaction failure: %w", recordErr)
		}
		if attempts < interactionMaxAttempts {
			return fmt.Errorf(
				"interaction projection attempt %d/%d on %s: %w",
				attempts, interactionMaxAttempts, stream, err,
			)
		}
		dlqStream := stream + interactionDLQSuffix
		if _, dlqErr := c.transport.AppendDurable(
			ctx,
			runtimemessaging.DurableMessage{
				Stream: dlqStream,
				Fields: interactionDLQFields(
					stream,
					message,
					err,
					attempts,
					errorClass,
				),
			},
		); dlqErr != nil {
			return fmt.Errorf("append interaction DLQ %s: %w", dlqStream, dlqErr)
		}
		if expireErr := c.transport.SetDurableRetention(
			ctx,
			dlqStream,
			interactionDLQRetention,
		); expireErr != nil {
			return fmt.Errorf("refresh interaction DLQ retention: %w", expireErr)
		}
		if markErr := c.failures.MarkInteractionDeadLettered(
			ctx,
			stream,
			message.ID,
		); markErr != nil {
			return fmt.Errorf(
				"mark interaction dead-letter state on %s: %w",
				stream,
				markErr,
			)
		}
		return nil
	}
	if err := c.transport.AckDurable(
		ctx,
		stream,
		interactionConsumerGroup,
		message.ID,
	); err != nil {
		return fmt.Errorf("ack interaction event on %s: %w", stream, err)
	}
	return c.failures.ClearInteractionFailure(ctx, stream, message.ID)
}

// RecoverDeadLetter releases a source PEL without reconstructing a message from
// the DLQ. The next scan reclaims the original source payload for processing.
func (c *InteractionNotificationConsumer) RecoverDeadLetter(
	ctx context.Context,
	sourceStream string,
	sourceStreamID string,
) error {
	if c == nil || c.failures == nil {
		return fmt.Errorf("interaction notification consumer is not configured")
	}
	sourceStream = strings.TrimSpace(sourceStream)
	sourceStreamID = strings.TrimSpace(sourceStreamID)
	if sourceStreamID == "" {
		return fmt.Errorf("interaction dead-letter source stream ID is required")
	}
	for _, stream := range c.streams {
		if stream == sourceStream {
			return c.failures.ClearInteractionFailure(
				ctx,
				sourceStream,
				sourceStreamID,
			)
		}
	}
	return fmt.Errorf("interaction dead-letter source stream is not configured")
}

// normalizeInteractionMessage 把两种 stream 形状（JSON payload 信封与扁平
// 字段）归一化为 InteractionStreamEvent。eventName 是 user 域扁平事件的
// 类型字段，eventType 是 content/circle 信封的类型字段。
func normalizeInteractionMessage(
	stream string,
	message runtimemessaging.StreamDelivery,
) (application.InteractionStreamEvent, error) {
	values := durableFieldsToMap(message.Fields)
	eventType := strings.TrimSpace(values["eventType"])
	if eventType == "" {
		eventType = strings.TrimSpace(values["eventName"])
	}
	eventID := strings.TrimSpace(values["eventId"])
	if eventType == "" || eventID == "" {
		return application.InteractionStreamEvent{},
			fmt.Errorf("interaction event on %s has no type or id", stream)
	}
	occurredAt := time.Time{}
	if raw := strings.TrimSpace(values["occurredAt"]); raw != "" {
		parsed, err := time.Parse(time.RFC3339Nano, raw)
		if err != nil {
			return application.InteractionStreamEvent{},
				fmt.Errorf("interaction event occurredAt is invalid: %w", err)
		}
		occurredAt = parsed.UTC()
	}
	return application.InteractionStreamEvent{
		Stream:     stream,
		MessageID:  message.ID,
		EventID:    eventID,
		EventType:  eventType,
		Values:     values,
		Payload:    []byte(values["payload"]),
		OccurredAt: occurredAt,
	}, nil
}

func uniqueStreamMessages(
	groups ...[]runtimemessaging.StreamDelivery,
) []runtimemessaging.StreamDelivery {
	seen := make(map[string]struct{})
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, messages := range groups {
		for _, message := range messages {
			if _, exists := seen[message.ID]; exists {
				continue
			}
			seen[message.ID] = struct{}{}
			result = append(result, message)
		}
	}
	return result
}

func interactionDLQFields(
	stream string,
	message runtimemessaging.StreamDelivery,
	cause error,
	attempts int64,
	errorClass string,
) []runtimemessaging.DurableField {
	messageValues := durableFieldsToMap(message.Fields)
	return irreversibleDeadLetterFields(irreversibleDeadLetterReference{
		SourceStream:   stream,
		SourceStreamID: message.ID,
		EventClass:     "interaction_notification",
		EventID:        messageValues["eventId"],
		Content:        messageValues["payload"],
		ErrorClass:     errorClass,
		Cause:          cause,
		Attempts:       attempts,
	})
}

func (c *InteractionNotificationConsumer) recordSuccess() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastSuccess = time.Now().UTC()
	c.lastFailure = nil
}

func (c *InteractionNotificationConsumer) recordFailure(err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastFailure = err
}
