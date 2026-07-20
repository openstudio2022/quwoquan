// Package stream 承载 notification-service 的 durable 事件消费 adapter。
// 互动事件经 Redis Stream consumer group at-least-once 投递，投影为
// AppMessage；幂等由 CreateAppMessage 的 idempotencyKey 唯一索引收敛。
package stream

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"sync"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/notification-service/internal/application"
)

const (
	interactionConsumerGroup            = "notification-service"
	interactionDLQSuffix                = ".notification-dlq"
	interactionMaxAttempts        int64 = 5
	interactionDLQRetention             = 7 * 24 * time.Hour
	interactionDefaultBatch       int64 = 50
	interactionDefaultMinIdleTime       = 30 * time.Second
)

// InteractionFailureStore 为每条 stream 消息保存独立失败计数，达到上限
// 才允许 dead-letter；成功或 dead-letter 后清除。
type InteractionFailureStore interface {
	RecordInteractionFailure(
		ctx context.Context,
		stream string,
		messageID string,
		eventID string,
		cause error,
	) (int64, error)
	ClearInteractionFailure(ctx context.Context, stream string, messageID string) error
}

type InteractionNotificationConsumer struct {
	redis       rtredis.Client
	facade      *application.AppMessageCommandFacade
	failures    InteractionFailureStore
	consumer    string
	streams     []string
	minIdle     time.Duration
	logger      *slog.Logger
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewInteractionNotificationConsumer(
	redis rtredis.Client,
	facade *application.AppMessageCommandFacade,
	failures InteractionFailureStore,
	consumer string,
	logger *slog.Logger,
) (*InteractionNotificationConsumer, error) {
	if redis == nil || facade == nil || failures == nil {
		return nil, fmt.Errorf(
			"interaction notification consumer requires redis, app message facade, and failure store",
		)
	}
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "notification-interaction-projector"
	}
	return &InteractionNotificationConsumer{
		redis:    redis,
		facade:   facade,
		failures: failures,
		consumer: consumer,
		streams:  append([]string(nil), application.InteractionNotificationStreams...),
		minIdle:  interactionDefaultMinIdleTime,
		logger:   logger,
	}, nil
}

func (c *InteractionNotificationConsumer) EnsureGroups(ctx context.Context) error {
	for _, stream := range c.streams {
		if err := c.redis.XGroupCreateMkStream(ctx, stream, interactionConsumerGroup, "0"); err != nil {
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
				slog.String("error", err.Error()))
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
	claimed, _, err := c.redis.XAutoClaim(
		ctx, stream, interactionConsumerGroup, c.consumer, c.minIdle, "0-0",
		interactionDefaultBatch,
	)
	if err != nil {
		return 0, fmt.Errorf("auto-claim %s: %w", stream, err)
	}
	fresh, err := c.redis.XReadGroup(ctx, interactionConsumerGroup, c.consumer,
		map[string]string{stream: ">"}, interactionDefaultBatch, 100*time.Millisecond)
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
	message rtredis.StreamMessage,
) error {
	event, err := normalizeInteractionMessage(stream, message)
	if err == nil {
		var commands []*application.CreateAppMessageCommand
		commands, err = application.ProjectInteractionNotification(event)
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
	if err != nil {
		attempts, recordErr := c.failures.RecordInteractionFailure(
			ctx, stream, message.ID, message.Values["eventId"], err,
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
		if _, dlqErr := c.redis.XAdd(
			ctx, dlqStream, interactionDLQValues(stream, message, err, attempts),
		); dlqErr != nil {
			return fmt.Errorf("append interaction DLQ %s: %w", dlqStream, dlqErr)
		}
		if expireErr := c.redis.Expire(ctx, dlqStream, interactionDLQRetention); expireErr != nil {
			return fmt.Errorf("refresh interaction DLQ retention: %w", expireErr)
		}
		if ackErr := c.redis.XAck(ctx, stream, interactionConsumerGroup, message.ID); ackErr != nil {
			return fmt.Errorf("ack dead-lettered interaction event: %w", ackErr)
		}
		return c.failures.ClearInteractionFailure(ctx, stream, message.ID)
	}
	if err := c.redis.XAck(ctx, stream, interactionConsumerGroup, message.ID); err != nil {
		return fmt.Errorf("ack interaction event on %s: %w", stream, err)
	}
	return c.failures.ClearInteractionFailure(ctx, stream, message.ID)
}

// normalizeInteractionMessage 把两种 stream 形状（JSON payload 信封与扁平
// 字段）归一化为 InteractionStreamEvent。eventName 是 user 域扁平事件的
// 类型字段，eventType 是 content/circle 信封的类型字段。
func normalizeInteractionMessage(
	stream string,
	message rtredis.StreamMessage,
) (application.InteractionStreamEvent, error) {
	values := message.Values
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

func uniqueStreamMessages(groups ...[]rtredis.StreamMessage) []rtredis.StreamMessage {
	seen := make(map[string]struct{})
	result := make([]rtredis.StreamMessage, 0)
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

func interactionDLQValues(
	stream string,
	message rtredis.StreamMessage,
	cause error,
	attempts int64,
) map[string]string {
	values := map[string]string{
		"sourceStream":   stream,
		"streamId":       message.ID,
		"error":          cause.Error(),
		"attempts":       strconv.FormatInt(attempts, 10),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
	for key, value := range message.Values {
		values[key] = value
	}
	return values
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
