package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"sync"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
)

const (
	ContentPostLifecycleStream       = "events.content.post_lifecycle"
	ContentPostLifecycleDLQ          = "events.content.post_lifecycle.dlq"
	contentPostConsumerGroup         = "circle-service"
	contentPostMaxAttempts     int64 = 5
	contentPostStreamRetention       = 7 * 24 * time.Hour
)

// ContentPostConsumer maintains Circle's typed external Post reference through
// Redis Stream consumer-group delivery. Mongo inbox and aggregate version make
// new delivery, pending reclaim and duplicate XADD converge to one projection.
type ContentPostConsumer struct {
	redis       rtredis.Client
	projection  placementports.PostLifecycleProjection
	failures    placementports.PostLifecycleFailureStore
	consumer    string
	minIdle     time.Duration
	logger      *slog.Logger
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewContentPostConsumer(
	redis rtredis.Client,
	projection placementports.PostLifecycleProjection,
	failures placementports.PostLifecycleFailureStore,
	consumer string,
	logger *slog.Logger,
) *ContentPostConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "circle-post-projection"
	}
	return &ContentPostConsumer{
		redis: redis, projection: projection, failures: failures,
		consumer: consumer, minIdle: 30 * time.Second, logger: logger,
	}
}

func (consumer *ContentPostConsumer) EnsureGroup(ctx context.Context) error {
	if consumer == nil || consumer.redis == nil {
		return fmt.Errorf("Content Post consumer Redis is not configured")
	}
	return consumer.redis.XGroupCreateMkStream(ctx, ContentPostLifecycleStream, contentPostConsumerGroup, "0")
}

func (consumer *ContentPostConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if consumer == nil || consumer.redis == nil || consumer.projection == nil || consumer.failures == nil {
		return 0, fmt.Errorf("Content Post consumer is not fully configured")
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.redis.XAutoClaim(
		ctx, ContentPostLifecycleStream, contentPostConsumerGroup,
		consumer.consumer, consumer.minIdle, "0-0", 50,
	)
	if err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	newMessages, err := consumer.redis.XReadGroup(ctx, contentPostConsumerGroup, consumer.consumer,
		map[string]string{ContentPostLifecycleStream: ">"}, 50, 200*time.Millisecond)
	if err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	messages := uniqueStreamMessages(claimed, newMessages)
	processed := 0
	var firstErr error
	for _, message := range messages {
		if err := consumer.processMessage(ctx, message); err != nil {
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		processed++
	}
	if firstErr != nil {
		consumer.recordFailure(firstErr)
		return processed, firstErr
	}
	consumer.recordSuccess()
	return processed, nil
}

func (consumer *ContentPostConsumer) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 250 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(ctx, "Content Post projection consume failed", slog.String("error", err.Error()))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *ContentPostConsumer) Healthy(maxStaleness time.Duration) error {
	if consumer == nil {
		return fmt.Errorf("Content Post consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return fmt.Errorf("Content Post consumer has not completed a scan")
	}
	if consumer.lastFailure != nil {
		return fmt.Errorf("Content Post consumer last failure: %w", consumer.lastFailure)
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return fmt.Errorf("Content Post consumer heartbeat is stale")
	}
	return nil
}

func (consumer *ContentPostConsumer) processMessage(ctx context.Context, message rtredis.StreamMessage) error {
	event, err := decodePostLifecycleMessage(message)
	if err == nil {
		err = consumer.projection.ApplyPostLifecycle(ctx, event)
	}
	if err != nil {
		attempts, recordErr := consumer.failures.RecordPostLifecycleFailure(ctx, message.ID, message.Values["eventId"], err)
		if recordErr != nil {
			return fmt.Errorf("record Content Post projection failure: %w", recordErr)
		}
		if attempts < contentPostMaxAttempts {
			return fmt.Errorf("Content Post projection attempt %d/%d: %w", attempts, contentPostMaxAttempts, err)
		}
		if _, dlqErr := consumer.redis.XAdd(ctx, ContentPostLifecycleDLQ, postLifecycleDLQValues(message, err, attempts)); dlqErr != nil {
			return fmt.Errorf("append Content Post projection DLQ: %w", dlqErr)
		}
		if expireErr := consumer.redis.Expire(ctx, ContentPostLifecycleDLQ, contentPostStreamRetention); expireErr != nil {
			return fmt.Errorf("refresh Content Post projection DLQ retention: %w", expireErr)
		}
		if ackErr := consumer.redis.XAck(ctx, ContentPostLifecycleStream, contentPostConsumerGroup, message.ID); ackErr != nil {
			return fmt.Errorf("ack dead-lettered Content Post event: %w", ackErr)
		}
		return consumer.failures.ClearPostLifecycleFailure(ctx, message.ID)
	}
	if err := consumer.redis.XAck(ctx, ContentPostLifecycleStream, contentPostConsumerGroup, message.ID); err != nil {
		return fmt.Errorf("ack Content Post lifecycle event: %w", err)
	}
	return consumer.failures.ClearPostLifecycleFailure(ctx, message.ID)
}

func decodePostLifecycleMessage(message rtredis.StreamMessage) (placementports.PostLifecycleEvent, error) {
	values := message.Values
	if strings.TrimSpace(values["aggregateType"]) != "Post" {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content lifecycle aggregateType must be Post")
	}
	version, err := strconv.ParseInt(strings.TrimSpace(values["aggregateVersion"]), 10, 64)
	if err != nil || version <= 0 {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content Post lifecycle aggregateVersion is invalid")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(values["occurredAt"]))
	if err != nil {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content Post lifecycle occurredAt is invalid")
	}
	var payload struct {
		ID       string `json:"_id"`
		PostID   string `json:"postId"`
		AuthorID string `json:"authorId"`
		Status   string `json:"status"`
	}
	if err := json.Unmarshal([]byte(values["payload"]), &payload); err != nil {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("decode Content Post lifecycle payload: %w", err)
	}
	postID := strings.TrimSpace(values["aggregateId"])
	payloadPostID := strings.TrimSpace(payload.ID)
	if payloadPostID == "" {
		payloadPostID = strings.TrimSpace(payload.PostID)
	}
	if postID == "" || payloadPostID != "" && payloadPostID != postID {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content Post lifecycle aggregate identity mismatch")
	}
	event := placementports.PostLifecycleEvent{
		EventID: strings.TrimSpace(values["eventId"]), EventType: strings.TrimSpace(values["eventType"]),
		PostID: postID, PostVersion: version, OwnerPersonaID: strings.TrimSpace(payload.AuthorID),
		State: strings.TrimSpace(payload.Status), OccurredAt: occurredAt.UTC(),
	}
	if event.EventID == "" || event.EventType == "" {
		return placementports.PostLifecycleEvent{}, fmt.Errorf("Content Post lifecycle event identity is incomplete")
	}
	return event, nil
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

func postLifecycleDLQValues(message rtredis.StreamMessage, cause error, attempts int64) map[string]string {
	values := map[string]string{
		"sourceStream": ContentPostLifecycleStream, "streamId": message.ID,
		"error": cause.Error(), "attempts": strconv.FormatInt(attempts, 10),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
	for key, value := range message.Values {
		values[key] = value
	}
	return values
}

func (consumer *ContentPostConsumer) recordSuccess() {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailure = nil
}

func (consumer *ContentPostConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailure = err
}
