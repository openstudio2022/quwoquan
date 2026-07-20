package messaging

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/circle-service/internal/application"
)

const (
	UserAccountEventStream = "events.user.account"
	UserAccountClosedDLQ   = "events.user.account.circle-service.dlq"

	userAccountClosedGroup          = "circle-service-user-account-closed"
	userAccountClosedDLQTTL         = 7 * 24 * time.Hour
	defaultClosedBatchSize    int64 = 50
	defaultClosedAttempts     int64 = 5
	defaultClosedMinIdle            = 30 * time.Second
	defaultClosedReadBlock          = 100 * time.Millisecond
	defaultClosedPollInterval       = 250 * time.Millisecond
)

var errUnsupportedUserAccountEvent = errors.New(
	"unsupported events.user.account event",
)

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
	ReadBlock    time.Duration
	PollInterval time.Duration
}

func DefaultUserAccountClosedConsumerConfig() UserAccountClosedConsumerConfig {
	return UserAccountClosedConsumerConfig{
		BatchSize:    defaultClosedBatchSize,
		MaxAttempts:  defaultClosedAttempts,
		MinIdle:      defaultClosedMinIdle,
		ReadBlock:    defaultClosedReadBlock,
		PollInterval: defaultClosedPollInterval,
	}
}

func normalizeUserAccountClosedConsumerConfig(
	config UserAccountClosedConsumerConfig,
) UserAccountClosedConsumerConfig {
	if config.BatchSize <= 0 {
		config.BatchSize = defaultClosedBatchSize
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = defaultClosedAttempts
	}
	if config.MinIdle < 0 {
		config.MinIdle = defaultClosedMinIdle
	}
	if config.ReadBlock < 0 {
		config.ReadBlock = defaultClosedReadBlock
	}
	if config.PollInterval <= 0 {
		config.PollInterval = defaultClosedPollInterval
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
) (*UserAccountClosedConsumer, error) {
	return NewUserAccountClosedConsumerWithConfig(
		redis,
		projection,
		failures,
		consumer,
		logger,
		DefaultUserAccountClosedConsumerConfig(),
	)
}

func NewUserAccountClosedConsumerWithConfig(
	redis rtredis.Client,
	projection application.UserAccountClosedProjection,
	failures UserAccountClosedFailureStore,
	consumer string,
	logger *slog.Logger,
	config UserAccountClosedConsumerConfig,
) (*UserAccountClosedConsumer, error) {
	if redis == nil || projection == nil || failures == nil {
		return nil, errors.New(
			"circle UserAccountClosed consumer requires Redis, projection, and failure store",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New(
			"circle UserAccountClosed consumer name is required",
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
		config:     normalizeUserAccountClosedConsumerConfig(config),
		logger:     logger,
	}, nil
}

func (consumer *UserAccountClosedConsumer) EnsureGroup(
	ctx context.Context,
) error {
	if consumer == nil || consumer.redis == nil {
		return errors.New(
			"circle UserAccountClosed consumer is not configured",
		)
	}
	if err := consumer.redis.XGroupCreateMkStream(
		ctx,
		UserAccountEventStream,
		userAccountClosedGroup,
		"0",
	); err != nil {
		return fmt.Errorf(
			"ensure circle UserAccountClosed consumer group: %w",
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
			"circle UserAccountClosed consumer is not fully configured",
		)
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.redis.XAutoClaim(
		ctx,
		UserAccountEventStream,
		userAccountClosedGroup,
		consumer.consumer,
		consumer.config.MinIdle,
		"0-0",
		consumer.config.BatchSize,
	)
	if err != nil {
		err = fmt.Errorf(
			"auto-claim circle UserAccountClosed events: %w",
			err,
		)
		consumer.recordFailure(err)
		return 0, err
	}
	fresh, err := consumer.redis.XReadGroup(
		ctx,
		userAccountClosedGroup,
		consumer.consumer,
		map[string]string{UserAccountEventStream: ">"},
		consumer.config.BatchSize,
		consumer.config.ReadBlock,
	)
	if err != nil {
		err = fmt.Errorf("read circle UserAccountClosed events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}

	processed := 0
	var firstErr error
	for _, message := range uniqueUserAccountMessages(claimed, fresh) {
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

func (consumer *UserAccountClosedConsumer) processMessage(
	ctx context.Context,
	message rtredis.StreamMessage,
) error {
	startedAt := time.Now()
	event, err := decodeUserAccountClosed(message.Values)
	if errors.Is(err, errUnsupportedUserAccountEvent) {
		if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		recordUserAccountClosedOutcome("ignored")
		return nil
	}
	if err == nil {
		var result application.UserAccountClosedApplyResult
		result, err = consumer.projection.ApplyUserAccountClosed(ctx, event)
		if err == nil {
			if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
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

	attempts, recordErr := consumer.failures.RecordUserAccountClosedFailure(
		ctx,
		message.ID,
		message.Values["eventId"],
		err,
	)
	if recordErr != nil {
		return fmt.Errorf(
			"record circle UserAccountClosed failure: %w",
			recordErr,
		)
	}
	if attempts < consumer.config.MaxAttempts {
		recordUserAccountClosedOutcome("retry")
		return fmt.Errorf(
			"circle UserAccountClosed attempt %d/%d failed: %w",
			attempts,
			consumer.config.MaxAttempts,
			err,
		)
	}
	errorDigest := irreversibleDigest(err.Error())
	if _, dlqErr := consumer.redis.XAdd(
		ctx,
		UserAccountClosedDLQ,
		userAccountClosedDLQValues(message, errorDigest, attempts),
	); dlqErr != nil {
		return fmt.Errorf(
			"append circle UserAccountClosed DLQ: %w",
			dlqErr,
		)
	}
	if expireErr := consumer.redis.Expire(
		ctx,
		UserAccountClosedDLQ,
		userAccountClosedDLQTTL,
	); expireErr != nil {
		return fmt.Errorf(
			"set circle UserAccountClosed DLQ retention: %w",
			expireErr,
		)
	}
	if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
		return ackErr
	}
	recordUserAccountClosedOutcome("dlq")
	consumer.logger.ErrorContext(
		ctx,
		"circle UserAccountClosed event moved to DLQ",
		slog.String("streamId", message.ID),
		slog.String("errorDigest", errorDigest),
		slog.Int64("attempts", attempts),
	)
	return nil
}

func (consumer *UserAccountClosedConsumer) ackAndClear(
	ctx context.Context,
	messageID string,
) error {
	if err := consumer.failures.ClearUserAccountClosedFailure(
		ctx,
		messageID,
	); err != nil {
		return fmt.Errorf(
			"clear circle UserAccountClosed failure receipt: %w",
			err,
		)
	}
	if err := consumer.redis.XAck(
		ctx,
		UserAccountEventStream,
		userAccountClosedGroup,
		messageID,
	); err != nil {
		return fmt.Errorf("ack circle UserAccountClosed event: %w", err)
	}
	return nil
}

func (consumer *UserAccountClosedConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(consumer.config.PollInterval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil &&
			ctx.Err() == nil {
			consumer.logger.ErrorContext(
				ctx,
				"circle UserAccountClosed consumer scan failed",
				slog.String("errorDigest", irreversibleDigest(err.Error())),
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
			"circle UserAccountClosed consumer is not configured",
		)
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return errors.New(
			"circle UserAccountClosed consumer has not completed a scan",
		)
	}
	if consumer.lastFailure != nil {
		return fmt.Errorf(
			"circle UserAccountClosed consumer last scan failed: %w",
			consumer.lastFailure,
		)
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New(
			"circle UserAccountClosed consumer heartbeat is stale",
		)
	}
	return nil
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
