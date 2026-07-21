package mq

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

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/application"
)

const (
	CircleGroupEventStream           = "events.circle.groups"
	CircleGroupMembershipEventStream = "events.circle.group-memberships"

	CircleGroupProvisionerConsumerGroup = "chat-circle-group-conversation-provisioner"
	CircleGroupMembershipConsumerGroup  = "chat-conversation-membership-projector"

	circleGroupCreatedEventType               = "CircleGroupCreated"
	circleGroupArchivedEventType              = "CircleGroupArchived"
	circleGroupMembershipActivatedEventType   = "CircleGroupMembershipActivated"
	circleGroupMembershipLeftEventType        = "CircleGroupMembershipLeft"
	circleGroupMembershipRemovedEventType     = "CircleGroupMembershipRemoved"
	circleGroupMembershipRoleChangedEventType = "CircleGroupMembershipRoleChanged"

	defaultCircleGroupChatSyncBatchSize   = int64(50)
	defaultCircleGroupChatSyncMaxAttempts = int64(5)
	defaultCircleGroupChatSyncMinIdle     = 30 * time.Second
	defaultCircleGroupChatSyncPoll        = 250 * time.Millisecond
	defaultCircleGroupChatSyncReadBlock   = 100 * time.Millisecond
	circleGroupChatSyncDLQTTL             = 7 * 24 * time.Hour
)

var errUnsupportedCircleGroupChatSyncEvent = errors.New("unsupported circle group chat sync event")

// CircleGroupChatSyncFailureStore keeps poison-message attempt counts outside
// Redis pending state. A message is ACKed only after the Chat projection
// commits or after its immutable DLQ record is successfully retained.
type CircleGroupChatSyncFailureStore interface {
	RecordCircleGroupChatSyncFailure(
		ctx context.Context,
		messageKey string,
		eventID string,
		errorDigest string,
	) (int64, error)
	ClearCircleGroupChatSyncFailure(ctx context.Context, messageKey string) error
}

type CircleGroupChatSyncConsumerConfig struct {
	Stream       string
	Group        string
	DLQ          string
	BatchSize    int64
	MaxAttempts  int64
	MinIdle      time.Duration
	PollInterval time.Duration
	ReadBlock    time.Duration
}

func DefaultCircleGroupProvisionerConsumerConfig() CircleGroupChatSyncConsumerConfig {
	return CircleGroupChatSyncConsumerConfig{
		Stream:       CircleGroupEventStream,
		Group:        CircleGroupProvisionerConsumerGroup,
		DLQ:          "events.circle.groups.chat-circle-group-conversation-provisioner.dlq",
		BatchSize:    defaultCircleGroupChatSyncBatchSize,
		MaxAttempts:  defaultCircleGroupChatSyncMaxAttempts,
		MinIdle:      defaultCircleGroupChatSyncMinIdle,
		PollInterval: defaultCircleGroupChatSyncPoll,
		ReadBlock:    defaultCircleGroupChatSyncReadBlock,
	}
}

func DefaultCircleGroupMembershipConsumerConfig() CircleGroupChatSyncConsumerConfig {
	return CircleGroupChatSyncConsumerConfig{
		Stream:       CircleGroupMembershipEventStream,
		Group:        CircleGroupMembershipConsumerGroup,
		DLQ:          "events.circle.group-memberships.chat-conversation-membership-projector.dlq",
		BatchSize:    defaultCircleGroupChatSyncBatchSize,
		MaxAttempts:  defaultCircleGroupChatSyncMaxAttempts,
		MinIdle:      defaultCircleGroupChatSyncMinIdle,
		PollInterval: defaultCircleGroupChatSyncPoll,
		ReadBlock:    defaultCircleGroupChatSyncReadBlock,
	}
}

func (config CircleGroupChatSyncConsumerConfig) withDefaults() CircleGroupChatSyncConsumerConfig {
	if config.BatchSize <= 0 {
		config.BatchSize = defaultCircleGroupChatSyncBatchSize
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = defaultCircleGroupChatSyncMaxAttempts
	}
	if config.MinIdle < 0 {
		config.MinIdle = defaultCircleGroupChatSyncMinIdle
	}
	if config.PollInterval <= 0 {
		config.PollInterval = defaultCircleGroupChatSyncPoll
	}
	if config.ReadBlock < 0 {
		config.ReadBlock = defaultCircleGroupChatSyncReadBlock
	}
	config.Stream = strings.TrimSpace(config.Stream)
	config.Group = strings.TrimSpace(config.Group)
	config.DLQ = strings.TrimSpace(config.DLQ)
	return config
}

type CircleGroupChatSyncConsumer struct {
	redis    rtredis.Client
	sync     application.CircleGroupChatSyncProjector
	failures CircleGroupChatSyncFailureStore
	consumer string
	config   CircleGroupChatSyncConsumerConfig
	logger   *slog.Logger

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure string
}

func NewCircleGroupChatSyncConsumer(
	redis rtredis.Client,
	syncService application.CircleGroupChatSyncProjector,
	failures CircleGroupChatSyncFailureStore,
	consumer string,
	logger *slog.Logger,
	config CircleGroupChatSyncConsumerConfig,
) (*CircleGroupChatSyncConsumer, error) {
	config = config.withDefaults()
	if redis == nil || syncService == nil || failures == nil {
		return nil, errors.New("circle group chat sync consumer requires redis, sync service and failure store")
	}
	if config.Stream == "" || config.Group == "" || config.DLQ == "" {
		return nil, errors.New("circle group chat sync consumer stream, group and DLQ are required")
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New("circle group chat sync consumer name is required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &CircleGroupChatSyncConsumer{
		redis: redis, sync: syncService, failures: failures, consumer: consumer,
		config: config, logger: logger,
	}, nil
}

func (c *CircleGroupChatSyncConsumer) EnsureGroup(ctx context.Context) error {
	if c == nil || c.redis == nil {
		return errors.New("circle group chat sync consumer is not configured")
	}
	if err := c.redis.XGroupCreateMkStream(ctx, c.config.Stream, c.config.Group, "0"); err != nil {
		return fmt.Errorf("ensure %s consumer group %s: %w", c.config.Stream, c.config.Group, err)
	}
	return nil
}

func (c *CircleGroupChatSyncConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.redis == nil || c.sync == nil || c.failures == nil {
		return 0, errors.New("circle group chat sync consumer is not fully configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		c.recordFailure(err)
		return 0, err
	}
	claimed, _, err := c.redis.XAutoClaim(
		ctx, c.config.Stream, c.config.Group, c.consumer, c.config.MinIdle, "0-0", c.config.BatchSize,
	)
	if err != nil {
		c.recordFailure(err)
		return 0, fmt.Errorf("auto-claim %s: %w", c.config.Stream, err)
	}
	fresh, err := c.redis.XReadGroup(
		ctx,
		c.config.Group,
		c.consumer,
		map[string]string{c.config.Stream: ">"},
		c.config.BatchSize,
		c.config.ReadBlock,
	)
	if err != nil {
		c.recordFailure(err)
		return 0, fmt.Errorf("read %s: %w", c.config.Stream, err)
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueCircleGroupChatSyncMessages(claimed, fresh) {
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

func (c *CircleGroupChatSyncConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(c.config.PollInterval)
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
				"circle group chat sync consume failed",
				slog.String("stream", c.config.Stream),
				slog.String("errorDigest", circleGroupChatSyncDigest(err.Error())),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *CircleGroupChatSyncConsumer) Healthy(maxStaleness time.Duration) error {
	if c == nil {
		return errors.New("circle group chat sync consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 30 * time.Second
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.lastSuccess.IsZero() {
		return fmt.Errorf("%s has not completed a scan", c.config.Group)
	}
	if c.lastFailure != "" {
		return fmt.Errorf("%s last failure digest: %s", c.config.Group, c.lastFailure)
	}
	if time.Since(c.lastSuccess) > maxStaleness {
		return fmt.Errorf("%s heartbeat is stale", c.config.Group)
	}
	return nil
}

func (c *CircleGroupChatSyncConsumer) processMessage(
	ctx context.Context,
	message rtredis.StreamMessage,
) error {
	startedAt := time.Now()
	event, err := decodeCircleGroupChatSyncEvent(c.config.Stream, message.Values)
	if errors.Is(err, errUnsupportedCircleGroupChatSyncEvent) {
		if ackErr := c.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		recordCircleGroupChatSyncOutcome(c.config.Stream, "ignored")
		return nil
	}
	if err == nil {
		err = c.sync.Apply(ctx, event)
		if err == nil {
			if ackErr := c.ackAndClear(ctx, message.ID); ackErr != nil {
				return ackErr
			}
			recordCircleGroupChatSyncOutcome(c.config.Stream, "applied")
			observeCircleGroupChatSyncApply(c.config.Stream, time.Since(startedAt))
			observeCircleGroupChatSyncLag(c.config.Stream, event.OccurredAt)
			return nil
		}
	}
	attempts, recordErr := c.failures.RecordCircleGroupChatSyncFailure(
		ctx,
		c.failureKey(message.ID),
		strings.TrimSpace(message.Values["eventId"]),
		circleGroupChatSyncDigest(err.Error()),
	)
	if recordErr != nil {
		return fmt.Errorf("record %s failure: %w", c.config.Group, recordErr)
	}
	if attempts < c.config.MaxAttempts {
		recordCircleGroupChatSyncOutcome(c.config.Stream, "retry")
		return fmt.Errorf("%s attempt %d/%d: %w", c.config.Group, attempts, c.config.MaxAttempts, err)
	}
	if _, dlqErr := c.redis.XAdd(ctx, c.config.DLQ, circleGroupChatSyncDLQValues(c.config.Stream, message, err, attempts)); dlqErr != nil {
		return fmt.Errorf("append %s DLQ: %w", c.config.Group, dlqErr)
	}
	if expireErr := c.redis.Expire(ctx, c.config.DLQ, circleGroupChatSyncDLQTTL); expireErr != nil {
		return fmt.Errorf("refresh %s DLQ retention: %w", c.config.Group, expireErr)
	}
	if ackErr := c.ackAndClear(ctx, message.ID); ackErr != nil {
		return ackErr
	}
	recordCircleGroupChatSyncOutcome(c.config.Stream, "dlq")
	c.logger.ErrorContext(
		ctx,
		"circle group chat sync moved event to DLQ",
		slog.String("stream", c.config.Stream),
		slog.String("streamId", message.ID),
		slog.String("errorDigest", circleGroupChatSyncDigest(err.Error())),
		slog.Int64("attempts", attempts),
	)
	return nil
}

func (c *CircleGroupChatSyncConsumer) ackAndClear(ctx context.Context, messageID string) error {
	if err := c.redis.XAck(ctx, c.config.Stream, c.config.Group, messageID); err != nil {
		return fmt.Errorf("ack %s message: %w", c.config.Group, err)
	}
	if err := c.failures.ClearCircleGroupChatSyncFailure(ctx, c.failureKey(messageID)); err != nil {
		recordCircleGroupChatSyncOutcome(c.config.Stream, "failure_state_cleanup_failed")
		c.logger.WarnContext(
			ctx,
			"circle group chat sync failure cleanup failed after ACK",
			slog.String("stream", c.config.Stream),
			slog.String("streamId", messageID),
			slog.String("errorDigest", circleGroupChatSyncDigest(err.Error())),
		)
	}
	return nil
}

func (c *CircleGroupChatSyncConsumer) failureKey(messageID string) string {
	return c.config.Stream + ":" + c.config.Group + ":" + messageID
}

func decodeCircleGroupChatSyncEvent(
	stream string,
	values map[string]string,
) (application.CircleGroupChatSourceEvent, error) {
	eventType := strings.TrimSpace(values["eventType"])
	if !isSupportedCircleGroupChatSyncEvent(stream, eventType) {
		return application.CircleGroupChatSourceEvent{}, errUnsupportedCircleGroupChatSyncEvent
	}
	var payload struct {
		GroupID            string `json:"groupId"`
		Version            int64  `json:"version"`
		CircleID           string `json:"circleId"`
		Name               string `json:"name"`
		CreatedByPersonaID string `json:"createdByPersonaId"`
		PersonaID          string `json:"personaId"`
		Role               string `json:"role"`
		State              string `json:"state"`
	}
	if err := json.Unmarshal([]byte(values["payload"]), &payload); err != nil {
		return application.CircleGroupChatSourceEvent{}, fmt.Errorf("decode %s payload: %w", eventType, err)
	}
	version, err := strconv.ParseInt(strings.TrimSpace(values["aggregateVersion"]), 10, 64)
	if err != nil || version <= 0 || payload.Version != version {
		return application.CircleGroupChatSourceEvent{}, fmt.Errorf(
			"%s aggregate version is invalid or differs from payload", eventType,
		)
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(values["occurredAt"]))
	if err != nil {
		return application.CircleGroupChatSourceEvent{}, fmt.Errorf("%s occurredAt is invalid: %w", eventType, err)
	}
	return application.CircleGroupChatSourceEvent{
		EventID:    strings.TrimSpace(values["eventId"]),
		EventType:  eventType,
		GroupID:    payload.GroupID,
		CircleID:   payload.CircleID,
		Version:    version,
		Name:       payload.Name,
		OwnerID:    payload.CreatedByPersonaID,
		UserID:     payload.PersonaID,
		Role:       payload.Role,
		State:      payload.State,
		OccurredAt: occurredAt.UTC(),
	}, nil
}

func isSupportedCircleGroupChatSyncEvent(stream, eventType string) bool {
	switch stream {
	case CircleGroupEventStream:
		return eventType == circleGroupCreatedEventType || eventType == circleGroupArchivedEventType
	case CircleGroupMembershipEventStream:
		switch eventType {
		case circleGroupMembershipActivatedEventType,
			circleGroupMembershipLeftEventType,
			circleGroupMembershipRemovedEventType,
			circleGroupMembershipRoleChangedEventType:
			return true
		default:
			return false
		}
	default:
		return false
	}
}

func uniqueCircleGroupChatSyncMessages(
	groups ...[]rtredis.StreamMessage,
) []rtredis.StreamMessage {
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

func circleGroupChatSyncDLQValues(
	stream string,
	message rtredis.StreamMessage,
	cause error,
	attempts int64,
) map[string]string {
	return map[string]string{
		"sourceStream":   stream,
		"sourceStreamId": message.ID,
		"eventType":      strings.TrimSpace(message.Values["eventType"]),
		"eventDigest":    circleGroupChatSyncDigest(message.Values["eventId"]),
		"errorDigest":    circleGroupChatSyncDigest(cause.Error()),
		"attempts":       strconv.FormatInt(attempts, 10),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
}

func (c *CircleGroupChatSyncConsumer) recordSuccess() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastSuccess = time.Now().UTC()
	c.lastFailure = ""
}

func (c *CircleGroupChatSyncConsumer) recordFailure(err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastFailure = circleGroupChatSyncDigest(err.Error())
}

func circleGroupChatSyncDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
