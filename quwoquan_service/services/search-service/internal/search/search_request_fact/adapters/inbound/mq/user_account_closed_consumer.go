package mq

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application"
)

const (
	UserAccountEventStream             = "events.user.account"
	UserAccountClosedConsumerGroup     = "search-service-user-account-closed"
	UserAccountClosedDeadLetterStream  = "events.user.account.search-service.dlq"
	userAccountClosedDefaultBatch      = int64(50)
	userAccountClosedDefaultAttempts   = int64(5)
	userAccountClosedDefaultMinIdle    = 30 * time.Second
	userAccountClosedDefaultPoll       = 250 * time.Millisecond
	userAccountClosedDeadLetterTimeout = 7 * 24 * time.Hour
)

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
	IsUserAccountClosedDeadLettered(
		ctx context.Context,
		stream string,
		messageID string,
	) (bool, error)
	MarkUserAccountClosedDeadLettered(
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

type UserAccountClosedTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
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
	transport  UserAccountClosedTransport
	projection application.UserAccountClosedProjection
	failures   UserAccountClosedFailureStore
	consumer   string
	config     UserAccountClosedConsumerConfig
	logger     *slog.Logger

	mu                sync.RWMutex
	lastSuccess       time.Time
	lastFailureDigest string
}

func NewUserAccountClosedConsumer(
	transport UserAccountClosedTransport,
	projection application.UserAccountClosedProjection,
	failures UserAccountClosedFailureStore,
	consumer string,
	logger *slog.Logger,
	config UserAccountClosedConsumerConfig,
) (*UserAccountClosedConsumer, error) {
	if transport == nil || projection == nil || failures == nil {
		return nil, errors.New(
			"search UserAccountClosed consumer requires message transport, projection, and failure store",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New(
			"search UserAccountClosed consumer name is required",
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
		config:     config.withDefaults(),
		logger:     logger,
	}, nil
}

func (consumer *UserAccountClosedConsumer) EnsureGroup(ctx context.Context) error {
	if consumer == nil || consumer.transport == nil {
		return errors.New("search UserAccountClosed consumer is not configured")
	}
	if err := consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		UserAccountEventStream,
		UserAccountClosedConsumerGroup,
		"0",
	); err != nil {
		return fmt.Errorf(
			"ensure search UserAccountClosed consumer group: %w",
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
			"search UserAccountClosed consumer is not configured",
		)
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.transport.ReclaimDurable(
		ctx,
		UserAccountEventStream,
		UserAccountClosedConsumerGroup,
		consumer.consumer,
		consumer.config.MinIdle,
		"0-0",
		consumer.config.BatchSize,
	)
	if err != nil {
		err = fmt.Errorf("auto-claim search UserAccountClosed events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}
	fresh, err := consumer.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   UserAccountEventStream,
			Group:    UserAccountClosedConsumerGroup,
			Consumer: consumer.consumer,
			Count:    consumer.config.BatchSize,
			Block:    100 * time.Millisecond,
		},
	)
	if err != nil {
		err = fmt.Errorf("read search UserAccountClosed events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}

	processed := 0
	var firstErr error
	for _, message := range uniqueMessages(claimed, fresh) {
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
		UserAccountEventStream,
		message.ID,
	)
	if stateErr != nil {
		return fmt.Errorf(
			"read search UserAccountClosed dead-letter state: %w",
			stateErr,
		)
	}
	if deadLettered {
		// The DLQ retains only an irreversible reference. The source PEL
		// remains authoritative and unacknowledged until controlled recovery.
		userAccountClosedConsumerTotal.WithLabelValues("held_for_recovery").Inc()
		return nil
	}
	event, err := decodeUserAccountClosed(message)
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

	return consumer.handleMessageFailure(ctx, message, err)
}

func (consumer *UserAccountClosedConsumer) handleMessageFailure(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
	cause error,
) error {
	attempts, recordErr := consumer.failures.RecordUserAccountClosedFailure(
		ctx,
		UserAccountEventStream,
		message.ID,
		durableFieldValue(message.Fields, "eventId"),
		cause,
	)
	if recordErr != nil {
		held, heldErr := consumer.failures.IsUserAccountClosedDeadLettered(
			ctx,
			UserAccountEventStream,
			message.ID,
		)
		if heldErr == nil && held {
			userAccountClosedConsumerTotal.WithLabelValues("held_for_recovery").Inc()
			return nil
		}
		return fmt.Errorf("record search UserAccountClosed failure: %w", recordErr)
	}
	if attempts < consumer.config.MaxAttempts {
		userAccountClosedConsumerTotal.WithLabelValues("retry").Inc()
		return fmt.Errorf(
			"search UserAccountClosed attempt %d/%d failed: %w",
			attempts,
			consumer.config.MaxAttempts,
			cause,
		)
	}
	if _, dlqErr := consumer.transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: UserAccountClosedDeadLetterStream,
			Fields: userAccountClosedDeadLetterFields(message, cause, attempts),
		},
	); dlqErr != nil {
		return fmt.Errorf("append search UserAccountClosed DLQ: %w", dlqErr)
	}
	if expireErr := consumer.transport.SetDurableRetention(
		ctx,
		UserAccountClosedDeadLetterStream,
		userAccountClosedDeadLetterTimeout,
	); expireErr != nil {
		return fmt.Errorf("set search UserAccountClosed DLQ retention: %w", expireErr)
	}
	if markErr := consumer.failures.MarkUserAccountClosedDeadLettered(
		ctx,
		UserAccountEventStream,
		message.ID,
	); markErr != nil {
		return fmt.Errorf(
			"mark search UserAccountClosed dead-letter state: %w",
			markErr,
		)
	}
	userAccountClosedConsumerTotal.WithLabelValues("dlq").Inc()
	consumer.logger.ErrorContext(
		ctx,
		"search UserAccountClosed event moved to DLQ",
		slog.String("errorDigest", irreversibleStreamDigest(cause.Error())),
		slog.Int64("attempts", attempts),
	)
	return nil
}

// RecoverDeadLetter releases the source PEL after remediation. It never
// rebuilds the original event from the sanitized dead-letter record.
func (consumer *UserAccountClosedConsumer) RecoverDeadLetter(
	ctx context.Context,
	sourceStreamID string,
) error {
	if consumer == nil || consumer.failures == nil {
		return errors.New("search UserAccountClosed consumer is not configured")
	}
	sourceStreamID = strings.TrimSpace(sourceStreamID)
	if sourceStreamID == "" {
		return errors.New("search UserAccountClosed dead-letter source stream ID is required")
	}
	deadLettered, err := consumer.failures.IsUserAccountClosedDeadLettered(
		ctx,
		UserAccountEventStream,
		sourceStreamID,
	)
	if err != nil {
		return fmt.Errorf(
			"verify search UserAccountClosed dead-letter state before recovery: %w",
			err,
		)
	}
	if !deadLettered {
		return nil
	}
	if err := consumer.failures.ClearUserAccountClosedFailure(
		ctx,
		UserAccountEventStream,
		sourceStreamID,
	); err != nil {
		return fmt.Errorf(
			"release search UserAccountClosed dead-letter state: %w",
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
		UserAccountEventStream,
		messageID,
	); err != nil {
		return fmt.Errorf("clear search UserAccountClosed failure: %w", err)
	}
	if err := consumer.transport.AckDurable(
		ctx,
		UserAccountEventStream,
		UserAccountClosedConsumerGroup,
		messageID,
	); err != nil {
		return fmt.Errorf("ack search UserAccountClosed event: %w", err)
	}
	return nil
}

func (consumer *UserAccountClosedConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(consumer.config.PollInterval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(
				ctx,
				"search UserAccountClosed consumer scan failed",
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
		return errors.New("search UserAccountClosed consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return errors.New(
			"search UserAccountClosed consumer has not completed a scan",
		)
	}
	if consumer.lastFailureDigest != "" {
		return fmt.Errorf(
			"search UserAccountClosed consumer last scan failed (digest=%s)",
			consumer.lastFailureDigest,
		)
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New("search UserAccountClosed consumer heartbeat is stale")
	}
	return nil
}

func uniqueMessages(
	groups ...[]runtimemessaging.StreamDelivery,
) []runtimemessaging.StreamDelivery {
	seen := make(map[string]struct{})
	messages := make([]runtimemessaging.StreamDelivery, 0)
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
	consumer.lastFailureDigest = ""
}

func (consumer *UserAccountClosedConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailureDigest = irreversibleStreamDigest(err.Error())
}
