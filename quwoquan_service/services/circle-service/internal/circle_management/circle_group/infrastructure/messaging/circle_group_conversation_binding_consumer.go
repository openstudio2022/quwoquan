package messaging

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
)

const (
	CircleGroupConversationProvisionedStream = "events.chat.circle-group-conversations"
	CircleGroupConversationBindingGroup      = "circle-group-conversation-binding-projector"
	CircleGroupConversationBindingDLQ        = "events.chat.circle-group-conversations.circle-group-conversation-binding-projector.dlq"

	circleGroupConversationProvisionedEventType = "CircleGroupConversationProvisioned"
	circleGroupConversationBindingBatchSize     = int64(50)
	circleGroupConversationBindingMaxAttempts   = int64(5)
	circleGroupConversationBindingMinIdle       = 30 * time.Second
	circleGroupConversationBindingPoll          = 250 * time.Millisecond
	circleGroupConversationBindingReadBlock     = 100 * time.Millisecond
	circleGroupConversationBindingDLQTTL        = 7 * 24 * time.Hour
)

var errUnsupportedCircleGroupConversationBindingEvent = errors.New("unsupported CircleGroup conversation binding event")

type CircleGroupConversationBindingConsumer struct {
	transport   runtimemessaging.DurableDeliveryTransport
	projector   groupapp.ConversationBindingProjection
	failures    groupapp.ConversationBindingFailureStore
	consumer    string
	logger      *slog.Logger
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure string
}

func NewCircleGroupConversationBindingConsumer(
	transport runtimemessaging.DurableDeliveryTransport,
	projector groupapp.ConversationBindingProjection,
	failures groupapp.ConversationBindingFailureStore,
	consumer string,
	logger *slog.Logger,
) (*CircleGroupConversationBindingConsumer, error) {
	if transport == nil || projector == nil || failures == nil {
		return nil, errors.New("CircleGroup conversation binding consumer requires transport, projector and failure store")
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New("CircleGroup conversation binding consumer name is required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &CircleGroupConversationBindingConsumer{
		transport: transport, projector: projector, failures: failures, consumer: consumer, logger: logger,
	}, nil
}

func (c *CircleGroupConversationBindingConsumer) EnsureGroup(ctx context.Context) error {
	if c == nil || c.transport == nil {
		return errors.New("CircleGroup conversation binding consumer transport is not configured")
	}
	if err := c.transport.EnsureDurableConsumerGroup(
		ctx,
		CircleGroupConversationProvisionedStream,
		CircleGroupConversationBindingGroup,
		"0",
	); err != nil {
		return fmt.Errorf("ensure CircleGroup conversation binding group: %w", err)
	}
	return nil
}

func (c *CircleGroupConversationBindingConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.transport == nil || c.projector == nil || c.failures == nil {
		return 0, errors.New("CircleGroup conversation binding consumer is not fully configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		c.recordFailure(err)
		return 0, err
	}
	claimed, _, err := c.transport.ReclaimDurable(
		ctx,
		CircleGroupConversationProvisionedStream,
		CircleGroupConversationBindingGroup,
		c.consumer,
		circleGroupConversationBindingMinIdle,
		"0-0",
		circleGroupConversationBindingBatchSize,
	)
	if err != nil {
		c.recordFailure(err)
		return 0, fmt.Errorf("auto-claim CircleGroup conversation bindings: %w", err)
	}
	fresh, err := c.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   CircleGroupConversationProvisionedStream,
			Group:    CircleGroupConversationBindingGroup,
			Consumer: c.consumer,
			Count:    circleGroupConversationBindingBatchSize,
			Block:    circleGroupConversationBindingReadBlock,
		},
	)
	if err != nil {
		c.recordFailure(err)
		return 0, fmt.Errorf("read CircleGroup conversation bindings: %w", err)
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueCircleGroupConversationBindingMessages(claimed, fresh) {
		if err := c.processMessage(ctx, message); err != nil {
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		processed++
	}
	if firstErr != nil {
		c.recordFailure(firstErr)
		return processed, firstErr
	}
	c.recordSuccess()
	return processed, nil
}

func (c *CircleGroupConversationBindingConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(circleGroupConversationBindingPoll)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		if _, err := c.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			c.logger.ErrorContext(
				ctx,
				"CircleGroup conversation binding consume failed",
				slog.String("errorDigest", circleGroupConversationBindingDigest(err.Error())),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *CircleGroupConversationBindingConsumer) Healthy(maxStaleness time.Duration) error {
	if c == nil {
		return errors.New("CircleGroup conversation binding consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 30 * time.Second
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.lastSuccess.IsZero() {
		return errors.New("CircleGroup conversation binding consumer has not completed a scan")
	}
	if c.lastFailure != "" {
		return fmt.Errorf("CircleGroup conversation binding consumer last failure digest: %s", c.lastFailure)
	}
	if time.Since(c.lastSuccess) > maxStaleness {
		return errors.New("CircleGroup conversation binding consumer heartbeat is stale")
	}
	return nil
}

func (c *CircleGroupConversationBindingConsumer) processMessage(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
) error {
	startedAt := time.Now()
	fact, err := decodeCircleGroupConversationBindingEvent(runtimemessaging.DurableFieldMap(message.Fields))
	if errors.Is(err, errUnsupportedCircleGroupConversationBindingEvent) {
		if ackErr := c.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		recordCircleGroupConversationBindingOutcome("ignored")
		return nil
	}
	if err == nil {
		err = c.projector.Apply(ctx, fact)
		if err == nil {
			if ackErr := c.ackAndClear(ctx, message.ID); ackErr != nil {
				return ackErr
			}
			recordCircleGroupConversationBindingOutcome("applied")
			observeCircleGroupConversationBindingDuration(time.Since(startedAt))
			return nil
		}
	}
	attempts, recordErr := c.failures.RecordCircleGroupConversationBindingFailure(
		ctx,
		message.ID,
		strings.TrimSpace(runtimemessaging.DurableFieldMap(message.Fields)["eventId"]),
		circleGroupConversationBindingDigest(err.Error()),
	)
	if recordErr != nil {
		return fmt.Errorf("record CircleGroup conversation binding failure: %w", recordErr)
	}
	if attempts < circleGroupConversationBindingMaxAttempts {
		recordCircleGroupConversationBindingOutcome("retry")
		return fmt.Errorf(
			"CircleGroup conversation binding attempt %d/%d: %w",
			attempts,
			circleGroupConversationBindingMaxAttempts,
			err,
		)
	}
	if _, dlqErr := c.transport.PublishDeadLetter(
		ctx,
		runtimemessaging.DeadLetterMessage{
			SourceStream:      CircleGroupConversationProvisionedStream,
			DestinationStream: CircleGroupConversationBindingDLQ,
			SourceID:          message.ID,
			Reason:            "projection_failed",
			Fields:            circleGroupConversationBindingDLQFields(message, err, attempts),
		},
	); dlqErr != nil {
		return fmt.Errorf("append CircleGroup conversation binding DLQ: %w", dlqErr)
	}
	if expireErr := c.transport.SetDurableRetention(ctx, CircleGroupConversationBindingDLQ, circleGroupConversationBindingDLQTTL); expireErr != nil {
		return fmt.Errorf("refresh CircleGroup conversation binding DLQ: %w", expireErr)
	}
	if ackErr := c.ackAndClear(ctx, message.ID); ackErr != nil {
		return ackErr
	}
	recordCircleGroupConversationBindingOutcome("dlq")
	c.logger.ErrorContext(
		ctx,
		"CircleGroup conversation binding moved event to DLQ",
		slog.String("streamId", message.ID),
		slog.String("errorDigest", circleGroupConversationBindingDigest(err.Error())),
		slog.Int64("attempts", attempts),
	)
	return nil
}

func (c *CircleGroupConversationBindingConsumer) ackAndClear(ctx context.Context, messageID string) error {
	if err := c.transport.AckDurable(
		ctx,
		CircleGroupConversationProvisionedStream,
		CircleGroupConversationBindingGroup,
		messageID,
	); err != nil {
		return fmt.Errorf("ack CircleGroup conversation binding: %w", err)
	}
	if err := c.failures.ClearCircleGroupConversationBindingFailure(ctx, messageID); err != nil {
		recordCircleGroupConversationBindingOutcome("failure_state_cleanup_failed")
		c.logger.WarnContext(
			ctx,
			"CircleGroup conversation binding failure cleanup failed after ACK",
			slog.String("streamId", messageID),
			slog.String("errorDigest", circleGroupConversationBindingDigest(err.Error())),
		)
	}
	return nil
}

func decodeCircleGroupConversationBindingEvent(
	values map[string]string,
) (groupapp.ConversationProvisionedFact, error) {
	if strings.TrimSpace(values["eventType"]) != circleGroupConversationProvisionedEventType {
		return groupapp.ConversationProvisionedFact{}, errUnsupportedCircleGroupConversationBindingEvent
	}
	var payload struct {
		ConversationID string `json:"conversationId"`
		CircleID       string `json:"circleId"`
		CircleGroupID  string `json:"circleGroupId"`
	}
	if err := json.Unmarshal([]byte(values["payload"]), &payload); err != nil {
		return groupapp.ConversationProvisionedFact{}, fmt.Errorf("decode CircleGroupConversationProvisioned payload: %w", err)
	}
	fact := groupapp.ConversationProvisionedFact{
		EventID:        strings.TrimSpace(values["eventId"]),
		CircleID:       strings.TrimSpace(payload.CircleID),
		CircleGroupID:  strings.TrimSpace(payload.CircleGroupID),
		ConversationID: strings.TrimSpace(payload.ConversationID),
	}
	if fact.EventID == "" || fact.CircleID == "" || fact.CircleGroupID == "" || fact.ConversationID == "" {
		return groupapp.ConversationProvisionedFact{}, errors.New("CircleGroupConversationProvisioned payload is incomplete")
	}
	return fact, nil
}

func uniqueCircleGroupConversationBindingMessages(
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

func circleGroupConversationBindingDLQFields(
	message runtimemessaging.StreamDelivery,
	cause error,
	attempts int64,
) []runtimemessaging.DurableField {
	values := runtimemessaging.DurableFieldMap(message.Fields)
	return runtimemessaging.DurableFieldsFromMap(map[string]string{
		"sourceStream":   CircleGroupConversationProvisionedStream,
		"sourceStreamId": message.ID,
		"eventType":      strings.TrimSpace(values["eventType"]),
		"eventDigest":    circleGroupConversationBindingDigest(values["eventId"]),
		"errorDigest":    circleGroupConversationBindingDigest(cause.Error()),
		"attempts":       strconv.FormatInt(attempts, 10),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
	})
}

func (c *CircleGroupConversationBindingConsumer) recordSuccess() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastSuccess = time.Now().UTC()
	c.lastFailure = ""
}

func (c *CircleGroupConversationBindingConsumer) recordFailure(err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastFailure = circleGroupConversationBindingDigest(err.Error())
}

func circleGroupConversationBindingDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
