package messaging

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"quwoquan_service/runtime/accountrestriction"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
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
	IsUserAccountClosedDeadLettered(
		ctx context.Context,
		messageID string,
	) (bool, error)
	MarkUserAccountClosedDeadLettered(
		ctx context.Context,
		messageID string,
	) error
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
	transport    runtimemessaging.DurableDeliveryTransport
	projection   application.UserAccountClosedProjection
	restrictions application.UserAccountRestrictionProjection
	failures     UserAccountClosedFailureStore
	consumer     string
	config       UserAccountClosedConsumerConfig
	logger       *slog.Logger

	mu                sync.RWMutex
	lastSuccess       time.Time
	lastFailureDigest string
}

func (consumer *UserAccountClosedConsumer) WithUserAccountRestrictionProjection(
	projection application.UserAccountRestrictionProjection,
) *UserAccountClosedConsumer {
	if consumer == nil || projection == nil {
		panic("circle user account restriction projection is required")
	}
	consumer.restrictions = projection
	return consumer
}

func NewUserAccountClosedConsumer(
	transport runtimemessaging.DurableDeliveryTransport,
	projection application.UserAccountClosedProjection,
	failures UserAccountClosedFailureStore,
	consumer string,
	logger *slog.Logger,
) (*UserAccountClosedConsumer, error) {
	return NewUserAccountClosedConsumerWithConfig(
		transport,
		projection,
		failures,
		consumer,
		logger,
		DefaultUserAccountClosedConsumerConfig(),
	)
}

func NewUserAccountClosedConsumerWithConfig(
	transport runtimemessaging.DurableDeliveryTransport,
	projection application.UserAccountClosedProjection,
	failures UserAccountClosedFailureStore,
	consumer string,
	logger *slog.Logger,
	config UserAccountClosedConsumerConfig,
) (*UserAccountClosedConsumer, error) {
	if transport == nil || projection == nil || failures == nil {
		return nil, errors.New(
			"circle UserAccountClosed consumer requires transport, projection, and failure store",
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
		transport:  transport,
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
	if consumer == nil || consumer.transport == nil {
		return errors.New(
			"circle UserAccountClosed consumer is not configured",
		)
	}
	if err := consumer.transport.EnsureDurableConsumerGroup(
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
		consumer.transport == nil ||
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
	claimed, _, err := consumer.transport.ReclaimDurable(
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
	readBlock := consumer.config.ReadBlock
	if readBlock <= 0 {
		readBlock = time.Millisecond
	}
	fresh, err := consumer.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   UserAccountEventStream,
			Group:    userAccountClosedGroup,
			Consumer: consumer.consumer,
			Count:    consumer.config.BatchSize,
			Block:    readBlock,
		},
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
	message runtimemessaging.StreamDelivery,
) error {
	startedAt := time.Now()
	deadLettered, stateErr := consumer.failures.IsUserAccountClosedDeadLettered(
		ctx,
		message.ID,
	)
	if stateErr != nil {
		return fmt.Errorf(
			"read circle UserAccountClosed dead-letter state: %w",
			stateErr,
		)
	}
	if deadLettered {
		// The DLQ stores only a sanitized source reference. Keep the source
		// PEL unacknowledged until a controlled recovery clears this marker.
		recordUserAccountClosedOutcome("held_for_recovery")
		return nil
	}
	values := runtimemessaging.DurableFieldMap(message.Fields)
	if restrictionEvent, restrictionErr := accountrestriction.Decode(
		values,
	); restrictionErr == nil {
		if consumer.restrictions == nil {
			return consumer.handleMessageFailure(
				ctx,
				message,
				values,
				errors.New(
					"circle user account restriction projection is not configured",
				),
			)
		}
		result, err := consumer.restrictions.Apply(ctx, restrictionEvent)
		if err != nil {
			return consumer.handleMessageFailure(ctx, message, values, err)
		}
		if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		outcome := "restriction_applied"
		if result.Replayed {
			outcome = "restriction_replayed"
		}
		recordUserAccountClosedOutcome(outcome)
		observeUserAccountClosedDuration(time.Since(startedAt))
		return nil
	} else if !errors.Is(restrictionErr, accountrestriction.ErrUnsupportedEvent) {
		return consumer.handleMessageFailure(
			ctx,
			message,
			values,
			restrictionErr,
		)
	}
	event, err := decodeUserAccountClosed(values)
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
	return consumer.handleMessageFailure(ctx, message, values, err)
}

func (consumer *UserAccountClosedConsumer) handleMessageFailure(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
	values map[string]string,
	err error,
) error {
	attempts, recordErr := consumer.failures.RecordUserAccountClosedFailure(
		ctx,
		message.ID,
		values["eventId"],
		err,
	)
	if recordErr != nil {
		held, heldErr := consumer.failures.IsUserAccountClosedDeadLettered(
			ctx,
			message.ID,
		)
		if heldErr == nil && held {
			recordUserAccountClosedOutcome("held_for_recovery")
			return nil
		}
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
	if _, dlqErr := consumer.transport.PublishDeadLetter(
		ctx,
		runtimemessaging.DeadLetterMessage{
			SourceStream:      UserAccountEventStream,
			DestinationStream: UserAccountClosedDLQ,
			SourceID:          message.ID,
			Reason:            "user_account_closed_projection_failed",
			Fields:            userAccountClosedDLQFields(message, errorDigest, attempts),
		},
	); dlqErr != nil {
		return fmt.Errorf(
			"append circle UserAccountClosed DLQ: %w",
			dlqErr,
		)
	}
	if expireErr := consumer.transport.SetDurableRetention(
		ctx,
		UserAccountClosedDLQ,
		userAccountClosedDLQTTL,
	); expireErr != nil {
		return fmt.Errorf(
			"set circle UserAccountClosed DLQ retention: %w",
			expireErr,
		)
	}
	if markErr := consumer.failures.MarkUserAccountClosedDeadLettered(
		ctx,
		message.ID,
	); markErr != nil {
		return fmt.Errorf(
			"mark circle UserAccountClosed dead-letter state: %w",
			markErr,
		)
	}
	recordUserAccountClosedOutcome("dlq")
	consumer.logger.ErrorContext(
		ctx,
		"circle UserAccountClosed event moved to DLQ",
		slog.String("sourceStreamDigest", irreversibleDigest(message.ID)),
		slog.String("errorDigest", errorDigest),
		slog.Int64("attempts", attempts),
	)
	return nil
}

// RecoverDeadLetter releases the original source PEL after remediation. It
// never reconstructs a UserAccountClosed payload from the sanitized DLQ.
func (consumer *UserAccountClosedConsumer) RecoverDeadLetter(
	ctx context.Context,
	sourceStreamID string,
) error {
	if consumer == nil || consumer.failures == nil {
		return errors.New("circle UserAccountClosed consumer is not configured")
	}
	sourceStreamID = strings.TrimSpace(sourceStreamID)
	if sourceStreamID == "" {
		return errors.New(
			"circle UserAccountClosed dead-letter source stream ID is required",
		)
	}
	deadLettered, err := consumer.failures.IsUserAccountClosedDeadLettered(
		ctx,
		sourceStreamID,
	)
	if err != nil {
		return fmt.Errorf(
			"verify circle UserAccountClosed dead-letter state before recovery: %w",
			err,
		)
	}
	if !deadLettered {
		return nil
	}
	if err := consumer.failures.ClearUserAccountClosedFailure(
		ctx,
		sourceStreamID,
	); err != nil {
		return fmt.Errorf(
			"release circle UserAccountClosed dead-letter state: %w",
			err,
		)
	}
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
	if err := consumer.transport.AckDurable(
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
	if consumer.lastFailureDigest != "" {
		return fmt.Errorf(
			"circle UserAccountClosed consumer last scan failed (digest=%s)",
			consumer.lastFailureDigest,
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
	consumer.lastFailureDigest = ""
}

func (consumer *UserAccountClosedConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailureDigest = irreversibleDigest(err.Error())
}
