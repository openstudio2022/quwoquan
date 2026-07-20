// Package stream 承载 notification-service 的 durable 事件消费 adapter。
package stream

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/notification-service/internal/application"
)

const (
	UserAccountEventStream             = "events.user.account"
	UserAccountClosedConsumerGroup     = "notification-service-user-account-closed"
	UserAccountClosedDeadLetterStream  = "events.user.account.notification-service.dlq"
	userAccountClosedDefaultBatch      = int64(50)
	userAccountClosedDefaultAttempts   = int64(5)
	userAccountClosedDefaultMinIdle    = 30 * time.Second
	userAccountClosedDefaultPoll       = 250 * time.Millisecond
	userAccountClosedDeadLetterTimeout = 7 * 24 * time.Hour
)

var errUnsupportedUserAccountEvent = errors.New("unsupported user account event")

// UserAccountClosedFailureStore 保存逐 stream message 的有限重试次数。
// 达到上限且 DLQ 落盘前，consumer 不得 ACK。
type UserAccountClosedFailureStore interface {
	RecordUserAccountClosedFailure(
		ctx context.Context,
		stream string,
		messageID string,
		eventID string,
		cause error,
	) (int64, error)
	ClearUserAccountClosedFailure(
		ctx context.Context,
		stream string,
		messageID string,
	) error
}

type UserAccountClosedConsumerConfig struct {
	BatchSize    int64
	MaxAttempts  int64
	MinIdle      time.Duration
	PollInterval time.Duration
}

func DefaultUserAccountClosedConsumerConfig() UserAccountClosedConsumerConfig {
	return UserAccountClosedConsumerConfig{
		BatchSize:    userAccountClosedDefaultBatch,
		MaxAttempts:  userAccountClosedDefaultAttempts,
		MinIdle:      userAccountClosedDefaultMinIdle,
		PollInterval: userAccountClosedDefaultPoll,
	}
}

func (config UserAccountClosedConsumerConfig) withDefaults() UserAccountClosedConsumerConfig {
	if config.BatchSize <= 0 {
		config.BatchSize = userAccountClosedDefaultBatch
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = userAccountClosedDefaultAttempts
	}
	if config.MinIdle < 0 {
		config.MinIdle = userAccountClosedDefaultMinIdle
	}
	if config.PollInterval <= 0 {
		config.PollInterval = userAccountClosedDefaultPoll
	}
	return config
}

type UserAccountClosedConsumer struct {
	redis      rtredis.Client
	projection application.UserAccountClosedProjection
	failures   UserAccountClosedFailureStore
	consumer   string
	config     UserAccountClosedConsumerConfig
	logger     *slog.Logger

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
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
		return nil, errors.New(
			"notification UserAccountClosed consumer requires redis, projection, and failure store",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New(
			"notification UserAccountClosed consumer name is required",
		)
	}
	if logger == nil {
		logger = slog.Default()
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

func (consumer *UserAccountClosedConsumer) EnsureGroup(ctx context.Context) error {
	if consumer == nil || consumer.redis == nil {
		return errors.New(
			"notification UserAccountClosed consumer is not configured",
		)
	}
	if err := consumer.redis.XGroupCreateMkStream(
		ctx,
		UserAccountEventStream,
		UserAccountClosedConsumerGroup,
		"0",
	); err != nil {
		return fmt.Errorf(
			"ensure notification UserAccountClosed consumer group: %w",
			err,
		)
	}
	return nil
}

func (consumer *UserAccountClosedConsumer) ProcessOnce(
	ctx context.Context,
) (int, error) {
	if consumer == nil ||
		consumer.redis == nil ||
		consumer.projection == nil ||
		consumer.failures == nil {
		return 0, errors.New(
			"notification UserAccountClosed consumer is not configured",
		)
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.redis.XAutoClaim(
		ctx,
		UserAccountEventStream,
		UserAccountClosedConsumerGroup,
		consumer.consumer,
		consumer.config.MinIdle,
		"0-0",
		consumer.config.BatchSize,
	)
	if err != nil {
		err = fmt.Errorf(
			"auto-claim notification UserAccountClosed events: %w",
			err,
		)
		consumer.recordFailure(err)
		return 0, err
	}
	fresh, err := consumer.redis.XReadGroup(
		ctx,
		UserAccountClosedConsumerGroup,
		consumer.consumer,
		map[string]string{UserAccountEventStream: ">"},
		consumer.config.BatchSize,
		100*time.Millisecond,
	)
	if err != nil {
		err = fmt.Errorf("read notification UserAccountClosed events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}

	processed := 0
	var firstErr error
	for _, message := range uniqueUserAccountClosedMessages(claimed, fresh) {
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

func (consumer *UserAccountClosedConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(consumer.config.PollInterval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(
				ctx,
				"notification UserAccountClosed consumer scan failed",
				slog.String("errorDigest", irreversibleStreamDigest(err.Error())),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *UserAccountClosedConsumer) Healthy(
	maxStaleness time.Duration,
) error {
	if consumer == nil {
		return errors.New(
			"notification UserAccountClosed consumer is not configured",
		)
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return errors.New(
			"notification UserAccountClosed consumer has not completed a scan",
		)
	}
	if consumer.lastFailure != nil {
		return fmt.Errorf(
			"notification UserAccountClosed consumer last scan failed: %w",
			consumer.lastFailure,
		)
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New(
			"notification UserAccountClosed consumer heartbeat is stale",
		)
	}
	return nil
}

func (consumer *UserAccountClosedConsumer) processMessage(
	ctx context.Context,
	message rtredis.StreamMessage,
) error {
	startedAt := time.Now()
	event, err := decodeNotificationUserAccountClosed(message)
	if errors.Is(err, errUnsupportedUserAccountEvent) {
		if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		userAccountClosedConsumerTotal.WithLabelValues("ignored").Inc()
		return nil
	}
	if err == nil {
		var result application.UserAccountClosedProjectionResult
		result, err = consumer.projection.ApplyUserAccountClosed(ctx, event)
		if err == nil {
			if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
				return ackErr
			}
			outcome := "applied"
			if result.Replayed {
				outcome = "replayed"
			}
			userAccountClosedConsumerTotal.WithLabelValues(outcome).Inc()
			userAccountClosedCleanupDuration.Observe(
				time.Since(startedAt).Seconds(),
			)
			return nil
		}
	}

	attempts, recordErr := consumer.failures.RecordUserAccountClosedFailure(
		ctx,
		UserAccountEventStream,
		message.ID,
		message.Values["eventId"],
		err,
	)
	if recordErr != nil {
		return fmt.Errorf(
			"record notification UserAccountClosed failure: %w",
			recordErr,
		)
	}
	if attempts < consumer.config.MaxAttempts {
		userAccountClosedConsumerTotal.WithLabelValues("retry").Inc()
		return fmt.Errorf(
			"notification UserAccountClosed attempt %d/%d failed: %w",
			attempts,
			consumer.config.MaxAttempts,
			err,
		)
	}
	if _, dlqErr := consumer.redis.XAdd(
		ctx,
		UserAccountClosedDeadLetterStream,
		userAccountClosedDeadLetterValues(message, err, attempts),
	); dlqErr != nil {
		return fmt.Errorf(
			"append notification UserAccountClosed DLQ: %w",
			dlqErr,
		)
	}
	if expireErr := consumer.redis.Expire(
		ctx,
		UserAccountClosedDeadLetterStream,
		userAccountClosedDeadLetterTimeout,
	); expireErr != nil {
		return fmt.Errorf(
			"set notification UserAccountClosed DLQ retention: %w",
			expireErr,
		)
	}
	if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
		return ackErr
	}
	userAccountClosedConsumerTotal.WithLabelValues("dlq").Inc()
	consumer.logger.ErrorContext(
		ctx,
		"notification UserAccountClosed event moved to DLQ",
		slog.String("errorDigest", irreversibleStreamDigest(err.Error())),
		slog.Int64("attempts", attempts),
	)
	return nil
}

func (consumer *UserAccountClosedConsumer) ackAndClear(
	ctx context.Context,
	messageID string,
) error {
	if err := consumer.redis.XAck(
		ctx,
		UserAccountEventStream,
		UserAccountClosedConsumerGroup,
		messageID,
	); err != nil {
		return fmt.Errorf(
			"ack notification UserAccountClosed event: %w",
			err,
		)
	}
	if err := consumer.failures.ClearUserAccountClosedFailure(
		ctx,
		UserAccountEventStream,
		messageID,
	); err != nil {
		return fmt.Errorf(
			"clear notification UserAccountClosed failure: %w",
			err,
		)
	}
	return nil
}

func uniqueUserAccountClosedMessages(
	groups ...[]rtredis.StreamMessage,
) []rtredis.StreamMessage {
	seen := make(map[string]struct{})
	messages := make([]rtredis.StreamMessage, 0)
	for _, group := range groups {
		for _, message := range group {
			if _, exists := seen[message.ID]; exists {
				continue
			}
			seen[message.ID] = struct{}{}
			messages = append(messages, message)
		}
	}
	return messages
}

func (consumer *UserAccountClosedConsumer) recordSuccess() {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailure = nil
}

func (consumer *UserAccountClosedConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailure = err
}
