package stream

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

const (
	UserAccountEventStream            = "events.user.account"
	UserAccountClosedConsumerGroup    = "integration-service-user-account-closed"
	UserAccountClosedDeadLetterStream = "events.user.account.integration-service.dlq"
	defaultBatchSize                  = int64(50)
	defaultMaxAttempts                = int64(5)
	defaultMinIdle                    = 30 * time.Second
	defaultPollInterval               = 250 * time.Millisecond
	deadLetterRetention               = 7 * 24 * time.Hour
)

type UserAccountClosedTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

type UserAccountClosedFailureStore interface {
	RecordUserAccountClosedFailure(
		ctx context.Context,
		stream string,
		messageID string,
		eventID string,
		errorClass string,
		cause error,
	) (int64, error)
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
		BatchSize:    defaultBatchSize,
		MaxAttempts:  defaultMaxAttempts,
		MinIdle:      defaultMinIdle,
		PollInterval: defaultPollInterval,
	}
}

func (config UserAccountClosedConsumerConfig) withDefaults() UserAccountClosedConsumerConfig {
	if config.BatchSize <= 0 {
		config.BatchSize = defaultBatchSize
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = defaultMaxAttempts
	}
	if config.MinIdle < 0 {
		config.MinIdle = defaultMinIdle
	}
	if config.PollInterval <= 0 {
		config.PollInterval = defaultPollInterval
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
			"integration UserAccountClosed consumer requires transport, projection, and failure store",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New("integration UserAccountClosed consumer name is required")
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
		return errors.New("integration UserAccountClosed consumer is not configured")
	}
	if err := consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		UserAccountEventStream,
		UserAccountClosedConsumerGroup,
		"0",
	); err != nil {
		return fmt.Errorf("ensure integration account closure consumer group: %w", err)
	}
	return nil
}

func (consumer *UserAccountClosedConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if consumer == nil || consumer.transport == nil ||
		consumer.projection == nil || consumer.failures == nil {
		return 0, errors.New("integration UserAccountClosed consumer is not configured")
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
		err = fmt.Errorf("reclaim integration account closure events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}
	fresh, err := consumer.transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream:   UserAccountEventStream,
		Group:    UserAccountClosedConsumerGroup,
		Consumer: consumer.consumer,
		Count:    consumer.config.BatchSize,
		Block:    100 * time.Millisecond,
	})
	if err != nil {
		err = fmt.Errorf("read integration account closure events: %w", err)
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
	deadLettered, err := consumer.failures.IsUserAccountClosedDeadLettered(
		ctx,
		UserAccountEventStream,
		message.ID,
	)
	if err != nil {
		return fmt.Errorf("read integration account closure dead-letter state: %w", err)
	}
	if deadLettered {
		userAccountClosedConsumerTotal.WithLabelValues("held_for_recovery").Inc()
		return nil
	}
	startedAt := time.Now()
	event, err := decodeUserAccountClosed(message)
	if errors.Is(err, errUnsupportedUserAccountEvent) {
		if err := consumer.ackAndClear(ctx, message.ID); err != nil {
			return err
		}
		userAccountClosedConsumerTotal.WithLabelValues("ignored").Inc()
		return nil
	}
	if err != nil {
		return consumer.handleFailure(ctx, message, "invalid_event", err)
	}
	result, err := consumer.projection.ApplyUserAccountClosed(ctx, event)
	if err != nil {
		errorClass := "projection_failed"
		if errors.Is(err, application.ErrUserAccountClosedEventIDConflict) {
			errorClass = "event_id_conflict"
		}
		return consumer.handleFailure(ctx, message, errorClass, err)
	}
	if err := consumer.ackAndClear(ctx, message.ID); err != nil {
		return err
	}
	outcome := "applied"
	if result.Replayed {
		outcome = "replayed"
	}
	userAccountClosedConsumerTotal.WithLabelValues(outcome).Inc()
	userAccountClosedCleanupDuration.Observe(time.Since(startedAt).Seconds())
	return nil
}

func (consumer *UserAccountClosedConsumer) handleFailure(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
	errorClass string,
	cause error,
) error {
	values := durableFieldsToMap(message.Fields)
	attempts, err := consumer.failures.RecordUserAccountClosedFailure(
		ctx,
		UserAccountEventStream,
		message.ID,
		values["eventId"],
		errorClass,
		cause,
	)
	if err != nil {
		return fmt.Errorf("record integration account closure failure: %w", err)
	}
	if attempts < consumer.config.MaxAttempts {
		userAccountClosedConsumerTotal.WithLabelValues("retry").Inc()
		return fmt.Errorf(
			"integration UserAccountClosed attempt %d/%d failed: %w",
			attempts,
			consumer.config.MaxAttempts,
			cause,
		)
	}
	if _, err := consumer.transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: UserAccountClosedDeadLetterStream,
		Fields: deadLetterFields(message, cause, attempts, errorClass),
	}); err != nil {
		return fmt.Errorf("append integration account closure dead letter: %w", err)
	}
	if err := consumer.transport.SetDurableRetention(
		ctx,
		UserAccountClosedDeadLetterStream,
		deadLetterRetention,
	); err != nil {
		return fmt.Errorf("set integration account closure dead-letter retention: %w", err)
	}
	if err := consumer.failures.MarkUserAccountClosedDeadLettered(
		ctx,
		UserAccountEventStream,
		message.ID,
	); err != nil {
		return err
	}
	userAccountClosedConsumerTotal.WithLabelValues("dlq").Inc()
	consumer.logger.ErrorContext(
		ctx,
		"integration UserAccountClosed event moved to DLQ",
		slog.String("errorDigest", irreversibleDigest(cause.Error())),
		slog.Int64("attempts", attempts),
	)
	return nil
}

func (consumer *UserAccountClosedConsumer) RecoverDeadLetter(
	ctx context.Context,
	sourceStreamID string,
) error {
	sourceStreamID = strings.TrimSpace(sourceStreamID)
	if consumer == nil || consumer.failures == nil || sourceStreamID == "" {
		return errors.New("integration account closure recovery requires source stream ID")
	}
	held, err := consumer.failures.IsUserAccountClosedDeadLettered(
		ctx,
		UserAccountEventStream,
		sourceStreamID,
	)
	if err != nil {
		return err
	}
	if !held {
		return nil
	}
	return consumer.failures.ClearUserAccountClosedFailure(
		ctx,
		UserAccountEventStream,
		sourceStreamID,
	)
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
		return err
	}
	if err := consumer.transport.AckDurable(
		ctx,
		UserAccountEventStream,
		UserAccountClosedConsumerGroup,
		messageID,
	); err != nil {
		return fmt.Errorf("ack integration account closure event: %w", err)
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
				"integration UserAccountClosed consumer scan failed",
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

func (consumer *UserAccountClosedConsumer) Healthy(maxStaleness time.Duration) error {
	if consumer == nil {
		return errors.New("integration UserAccountClosed consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return errors.New("integration UserAccountClosed consumer has not completed a scan")
	}
	if consumer.lastFailureDigest != "" {
		return fmt.Errorf(
			"integration UserAccountClosed consumer last scan failed (digest=%s)",
			consumer.lastFailureDigest,
		)
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New("integration UserAccountClosed consumer heartbeat is stale")
	}
	return nil
}

func uniqueMessages(groups ...[]runtimemessaging.StreamDelivery) []runtimemessaging.StreamDelivery {
	seen := make(map[string]struct{})
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, group := range groups {
		for _, message := range group {
			if _, exists := seen[message.ID]; exists {
				continue
			}
			seen[message.ID] = struct{}{}
			result = append(result, message)
		}
	}
	return result
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
