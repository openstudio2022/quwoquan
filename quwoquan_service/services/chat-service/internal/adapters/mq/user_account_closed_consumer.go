package mq

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
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
	UserAccountEventStream            = "events.user.account"
	userAccountClosedGroup            = "chat-service-user-account-closed"
	userAccountClosedDLQ              = "events.user.account.chat-service.dlq"
	defaultUserAccountClosedBatchSize = int64(50)
	defaultUserAccountClosedAttempts  = int64(5)
	defaultUserAccountClosedMinIdle   = 30 * time.Second
	defaultUserAccountClosedPoll      = 250 * time.Millisecond
	defaultUserAccountClosedReadBlock = 100 * time.Millisecond
	userAccountClosedDLQTTL           = 7 * 24 * time.Hour
)

var errUnsupportedUserAccountEvent = errors.New("unsupported user account event")

// UserAccountClosedFailureStore 保存逐 stream message 的失败次数。失败消息在
// 达到上限并成功写入 DLQ 前不得 ACK。
type UserAccountClosedFailureStore interface {
	RecordUserAccountClosedFailure(
		ctx context.Context,
		messageID string,
		eventID string,
		cause error,
	) (int64, error)
	ClearUserAccountClosedFailure(ctx context.Context, messageID string) error
}

type UserAccountClosedConsumerConfig struct {
	BatchSize    int64
	MaxAttempts  int64
	MinIdle      time.Duration
	PollInterval time.Duration
	ReadBlock    time.Duration
}

func DefaultUserAccountClosedConsumerConfig() UserAccountClosedConsumerConfig {
	return UserAccountClosedConsumerConfig{
		BatchSize:    defaultUserAccountClosedBatchSize,
		MaxAttempts:  defaultUserAccountClosedAttempts,
		MinIdle:      defaultUserAccountClosedMinIdle,
		PollInterval: defaultUserAccountClosedPoll,
		ReadBlock:    defaultUserAccountClosedReadBlock,
	}
}

func (config UserAccountClosedConsumerConfig) withDefaults() UserAccountClosedConsumerConfig {
	if config.BatchSize <= 0 {
		config.BatchSize = defaultUserAccountClosedBatchSize
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = defaultUserAccountClosedAttempts
	}
	if config.MinIdle < 0 {
		config.MinIdle = defaultUserAccountClosedMinIdle
	}
	if config.PollInterval <= 0 {
		config.PollInterval = defaultUserAccountClosedPoll
	}
	if config.ReadBlock < 0 {
		config.ReadBlock = defaultUserAccountClosedReadBlock
	}
	return config
}

type UserAccountClosedConsumer struct {
	redis       rtredis.Client
	projection  application.UserAccountClosedProjection
	failures    UserAccountClosedFailureStore
	consumer    string
	config      UserAccountClosedConsumerConfig
	logger      *slog.Logger
	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure string
}

func NewUserAccountClosedConsumer(
	redis rtredis.Client,
	projection application.UserAccountClosedProjection,
	failures UserAccountClosedFailureStore,
	consumer string,
	logger *slog.Logger,
	config UserAccountClosedConsumerConfig,
) (*UserAccountClosedConsumer, error) {
	if redis == nil || projection == nil || failures == nil {
		return nil, fmt.Errorf(
			"chat UserAccountClosed consumer requires redis, projection, and failure store",
		)
	}
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, fmt.Errorf("chat UserAccountClosed consumer name is required")
	}
	return &UserAccountClosedConsumer{
		redis:      redis,
		projection: projection,
		failures:   failures,
		consumer:   consumer,
		config:     config.withDefaults(),
		logger:     logger,
	}, nil
}

func (c *UserAccountClosedConsumer) EnsureGroup(ctx context.Context) error {
	if c == nil || c.redis == nil {
		return fmt.Errorf("chat UserAccountClosed consumer is not configured")
	}
	if err := c.redis.XGroupCreateMkStream(
		ctx,
		UserAccountEventStream,
		userAccountClosedGroup,
		"0",
	); err != nil {
		return fmt.Errorf("ensure chat UserAccountClosed consumer group: %w", err)
	}
	return nil
}

func (c *UserAccountClosedConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.redis == nil || c.projection == nil || c.failures == nil {
		return 0, fmt.Errorf("chat UserAccountClosed consumer is not fully configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		c.recordFailure(err)
		return 0, err
	}
	claimed, _, err := c.redis.XAutoClaim(
		ctx,
		UserAccountEventStream,
		userAccountClosedGroup,
		c.consumer,
		c.config.MinIdle,
		"0-0",
		c.config.BatchSize,
	)
	if err != nil {
		c.recordFailure(err)
		return 0, fmt.Errorf("auto-claim UserAccountClosed: %w", err)
	}
	fresh, err := c.redis.XReadGroup(
		ctx,
		userAccountClosedGroup,
		c.consumer,
		map[string]string{UserAccountEventStream: ">"},
		c.config.BatchSize,
		c.config.ReadBlock,
	)
	if err != nil {
		c.recordFailure(err)
		return 0, fmt.Errorf("read UserAccountClosed: %w", err)
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueUserAccountMessages(claimed, fresh) {
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

func (c *UserAccountClosedConsumer) Run(ctx context.Context) {
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
				"chat UserAccountClosed consume failed",
				slog.String("errorDigest", irreversibleUserAccountClosedDigest(err.Error())),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *UserAccountClosedConsumer) Healthy(
	maxStaleness time.Duration,
) error {
	if c == nil {
		return fmt.Errorf("chat UserAccountClosed consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.lastSuccess.IsZero() {
		return fmt.Errorf("chat UserAccountClosed consumer has not completed a scan")
	}
	if c.lastFailure != "" {
		return fmt.Errorf(
			"chat UserAccountClosed consumer last failure digest: %s",
			c.lastFailure,
		)
	}
	if time.Since(c.lastSuccess) > maxStaleness {
		return fmt.Errorf("chat UserAccountClosed consumer heartbeat is stale")
	}
	return nil
}

func (c *UserAccountClosedConsumer) processMessage(
	ctx context.Context,
	message rtredis.StreamMessage,
) error {
	startedAt := time.Now()
	event, err := decodeUserAccountClosed(message.Values)
	if errors.Is(err, errUnsupportedUserAccountEvent) {
		if ackErr := c.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		recordUserAccountClosedOutcome("ignored")
		return nil
	}
	if err == nil {
		var result application.UserAccountClosedApplyResult
		result, err = c.projection.ApplyUserAccountClosed(ctx, event)
		if err == nil {
			if ackErr := c.ackAndClear(ctx, message.ID); ackErr != nil {
				return ackErr
			}
			outcome := "applied"
			if result.Replayed {
				outcome = "replayed"
			}
			recordUserAccountClosedOutcome(outcome)
			observeUserAccountClosedDuration(time.Since(startedAt))
			return nil
		}
	}
	if err != nil {
		attempts, recordErr := c.failures.RecordUserAccountClosedFailure(
			ctx,
			message.ID,
			message.Values["eventId"],
			err,
		)
		if recordErr != nil {
			return fmt.Errorf(
				"record chat UserAccountClosed failure: %w",
				recordErr,
			)
		}
		if attempts < c.config.MaxAttempts {
			recordUserAccountClosedOutcome("retry")
			return fmt.Errorf(
				"chat UserAccountClosed attempt %d/%d: %w",
				attempts,
				c.config.MaxAttempts,
				err,
			)
		}
		if _, dlqErr := c.redis.XAdd(
			ctx,
			userAccountClosedDLQ,
			userAccountClosedDLQValues(message, err, attempts),
		); dlqErr != nil {
			return fmt.Errorf("append chat UserAccountClosed DLQ: %w", dlqErr)
		}
		if expireErr := c.redis.Expire(
			ctx,
			userAccountClosedDLQ,
			userAccountClosedDLQTTL,
		); expireErr != nil {
			return fmt.Errorf(
				"refresh chat UserAccountClosed DLQ retention: %w",
				expireErr,
			)
		}
		if ackErr := c.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		recordUserAccountClosedOutcome("dlq")
		c.logger.ErrorContext(
			ctx,
			"chat UserAccountClosed event moved to DLQ",
			slog.String("streamId", message.ID),
			slog.String("errorDigest", irreversibleUserAccountClosedDigest(err.Error())),
			slog.Int64("attempts", attempts),
		)
		return nil
	}
	return nil
}

func (c *UserAccountClosedConsumer) ackAndClear(
	ctx context.Context,
	messageID string,
) error {
	if err := c.redis.XAck(
		ctx,
		UserAccountEventStream,
		userAccountClosedGroup,
		messageID,
	); err != nil {
		return fmt.Errorf("ack chat UserAccountClosed: %w", err)
	}
	if err := c.failures.ClearUserAccountClosedFailure(ctx, messageID); err != nil {
		recordUserAccountClosedOutcome("failure_state_cleanup_failed")
		c.logger.WarnContext(
			ctx,
			"chat UserAccountClosed failure state cleanup failed after ACK",
			slog.String("streamId", messageID),
			slog.String("errorDigest", irreversibleUserAccountClosedDigest(err.Error())),
		)
	}
	return nil
}

func uniqueUserAccountMessages(
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

func userAccountClosedDLQValues(
	message rtredis.StreamMessage,
	cause error,
	attempts int64,
) map[string]string {
	return map[string]string{
		"sourceStream":   UserAccountEventStream,
		"sourceStreamId": message.ID,
		"eventName":      strings.TrimSpace(message.Values["eventName"]),
		"eventDigest": irreversibleUserAccountClosedDigest(
			message.Values["eventId"],
		),
		"errorDigest": irreversibleUserAccountClosedDigest(cause.Error()),
		"attempts":    strconv.FormatInt(attempts, 10),
		"deadLetteredAt": time.Now().
			UTC().
			Format(time.RFC3339Nano),
	}
}

func (c *UserAccountClosedConsumer) recordSuccess() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastSuccess = time.Now().UTC()
	c.lastFailure = ""
}

func (c *UserAccountClosedConsumer) recordFailure(err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastFailure = irreversibleUserAccountClosedDigest(err.Error())
}

func irreversibleUserAccountClosedDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}
