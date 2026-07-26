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
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
)

const (
	userAccountSecurityConsumerGroup    = "realtime-gateway-user-account-security"
	userAccountSecurityDeadLetterStream = "events.user.account.realtime-gateway.dlq"
	accountSecurityDefaultBatch         = int64(50)
	accountSecurityDefaultAttempts      = int64(5)
	accountSecurityDefaultMinIdle       = 30 * time.Second
	accountSecurityDefaultPoll          = 250 * time.Millisecond
	accountSecurityDefaultReadBlock     = 100 * time.Millisecond
	accountSecurityDeadLetterRetention  = 7 * 24 * time.Hour
)

// DurableMessageTransport keeps the source PEL explicit: a terminal failure
// remains recoverable from the original durable event rather than copying its
// PII payload into the DLQ.
type DurableMessageTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

type AccountSecurityFailureStore interface {
	RecordAccountSecurityFailure(
		ctx context.Context,
		stream, messageID, eventID, errorClass string,
		cause error,
	) (int64, error)
	IsAccountSecurityDeadLettered(
		ctx context.Context,
		stream, messageID string,
	) (bool, error)
	MarkAccountSecurityDeadLettered(
		ctx context.Context,
		stream, messageID string,
	) error
	ClearAccountSecurityFailure(
		ctx context.Context,
		stream, messageID string,
	) error
}

type AccountSecurityEvicter interface {
	EvictAccount(event application.AccountSecurityEvent)
}

type UserAccountSecurityConsumerConfig struct {
	BatchSize    int64
	MaxAttempts  int64
	MinIdle      time.Duration
	PollInterval time.Duration
	ReadBlock    time.Duration
}

func DefaultUserAccountSecurityConsumerConfig() UserAccountSecurityConsumerConfig {
	return UserAccountSecurityConsumerConfig{
		BatchSize:    accountSecurityDefaultBatch,
		MaxAttempts:  accountSecurityDefaultAttempts,
		MinIdle:      accountSecurityDefaultMinIdle,
		PollInterval: accountSecurityDefaultPoll,
		ReadBlock:    accountSecurityDefaultReadBlock,
	}
}

func (config UserAccountSecurityConsumerConfig) withDefaults() UserAccountSecurityConsumerConfig {
	if config.BatchSize <= 0 {
		config.BatchSize = accountSecurityDefaultBatch
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = accountSecurityDefaultAttempts
	}
	if config.MinIdle < 0 {
		config.MinIdle = accountSecurityDefaultMinIdle
	}
	if config.PollInterval <= 0 {
		config.PollInterval = accountSecurityDefaultPoll
	}
	if config.ReadBlock < 0 {
		config.ReadBlock = accountSecurityDefaultReadBlock
	}
	return config
}

type UserAccountSecurityConsumer struct {
	transport DurableMessageTransport
	gate      application.AccountSecurityGate
	relay     application.AccountSecurityRelay
	evicter   AccountSecurityEvicter
	failures  AccountSecurityFailureStore
	consumer  string
	config    UserAccountSecurityConsumerConfig
	logger    *slog.Logger

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure string
}

func NewUserAccountSecurityConsumer(
	transport DurableMessageTransport,
	gate application.AccountSecurityGate,
	relay application.AccountSecurityRelay,
	evicter AccountSecurityEvicter,
	failures AccountSecurityFailureStore,
	consumer string,
	logger *slog.Logger,
	config UserAccountSecurityConsumerConfig,
) (*UserAccountSecurityConsumer, error) {
	if transport == nil || gate == nil || relay == nil || evicter == nil ||
		failures == nil {
		return nil, errors.New(
			"realtime account security consumer requires transport, gate, relay, evicter and failure store",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New("realtime account security consumer name is required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &UserAccountSecurityConsumer{
		transport: transport,
		gate:      gate,
		relay:     relay,
		evicter:   evicter,
		failures:  failures,
		consumer:  consumer,
		config:    config.withDefaults(),
		logger:    logger,
	}, nil
}

func (consumer *UserAccountSecurityConsumer) EnsureGroup(
	ctx context.Context,
) error {
	if consumer == nil || consumer.transport == nil {
		return errors.New("realtime account security consumer is not configured")
	}
	if err := consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		userAccountEventStream,
		userAccountSecurityConsumerGroup,
		"0",
	); err != nil {
		return fmt.Errorf("ensure realtime account security consumer group: %w", err)
	}
	return nil
}

func (consumer *UserAccountSecurityConsumer) ProcessOnce(
	ctx context.Context,
) (int, error) {
	if consumer == nil || consumer.transport == nil || consumer.gate == nil ||
		consumer.relay == nil || consumer.evicter == nil || consumer.failures == nil {
		return 0, errors.New("realtime account security consumer is not configured")
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.transport.ReclaimDurable(
		ctx,
		userAccountEventStream,
		userAccountSecurityConsumerGroup,
		consumer.consumer,
		consumer.config.MinIdle,
		"0-0",
		consumer.config.BatchSize,
	)
	if err != nil {
		err = fmt.Errorf("reclaim realtime account security events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}
	fresh, err := consumer.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   userAccountEventStream,
			Group:    userAccountSecurityConsumerGroup,
			Consumer: consumer.consumer,
			Count:    consumer.config.BatchSize,
			Block:    consumer.config.ReadBlock,
		},
	)
	if err != nil {
		err = fmt.Errorf("read realtime account security events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueAccountSecurityMessages(claimed, fresh) {
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

func (consumer *UserAccountSecurityConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(consumer.config.PollInterval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(
				ctx,
				"realtime account security consumer scan failed",
				slog.String("errorDigest", application.ErrorDigest(err)),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *UserAccountSecurityConsumer) Healthy(
	maxStaleness time.Duration,
) error {
	if consumer == nil {
		return errors.New("realtime account security consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return errors.New("realtime account security consumer has not completed a scan")
	}
	if consumer.lastFailure != "" {
		return errors.New("realtime account security consumer last scan failed")
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New("realtime account security consumer heartbeat is stale")
	}
	return nil
}

func (consumer *UserAccountSecurityConsumer) RecoverDeadLetter(
	ctx context.Context,
	sourceStreamID string,
) error {
	if consumer == nil || consumer.failures == nil {
		return errors.New("realtime account security consumer is not configured")
	}
	sourceStreamID = strings.TrimSpace(sourceStreamID)
	if sourceStreamID == "" {
		return errors.New(
			"realtime account security dead-letter source stream ID is required",
		)
	}
	deadLettered, err := consumer.failures.IsAccountSecurityDeadLettered(
		ctx,
		userAccountEventStream,
		sourceStreamID,
	)
	if err != nil {
		return fmt.Errorf(
			"verify realtime account security dead-letter state before recovery: %w",
			err,
		)
	}
	if !deadLettered {
		return nil
	}
	return consumer.failures.ClearAccountSecurityFailure(
		ctx,
		userAccountEventStream,
		sourceStreamID,
	)
}

func (consumer *UserAccountSecurityConsumer) processMessage(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
) error {
	eventClass := accountSecurityEventClass(
		durableFieldValue(message.Fields, "eventName"),
	)
	deadLettered, err := consumer.failures.IsAccountSecurityDeadLettered(
		ctx,
		userAccountEventStream,
		message.ID,
	)
	if err != nil {
		return fmt.Errorf("read realtime account security failure state: %w", err)
	}
	if deadLettered {
		accountSecurityConsumerTotal.WithLabelValues(eventClass, "held_for_recovery").Inc()
		return nil
	}
	event, err := decodeUserAccountSecurityEvent(message)
	if errors.Is(err, errUnsupportedUserAccountSecurityEvent) {
		if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		accountSecurityConsumerTotal.WithLabelValues(eventClass, "ignored").Inc()
		return nil
	}
	startedAt := time.Now()
	errorClass := "invalid_event"
	if err == nil {
		var result application.AccountSecurityApplyResult
		result, err = consumer.gate.ApplyAccountSecurityEvent(ctx, event)
		if err == nil && result.Evict {
			consumer.evicter.EvictAccount(event)
			err = consumer.relay.PublishAccountSecurity(ctx, event)
			if err != nil {
				errorClass = "relay_unavailable"
			}
		}
		if err == nil {
			if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
				return ackErr
			}
			outcome := "applied"
			if result.Replayed {
				outcome = "replayed"
			}
			accountSecurityConsumerTotal.WithLabelValues(eventClass, outcome).Inc()
			accountSecurityConsumerDuration.Observe(time.Since(startedAt).Seconds())
			return nil
		}
		if errorClass == "invalid_event" {
			errorClass = accountSecurityErrorClass(err)
		}
	}
	attempts, recordErr := consumer.failures.RecordAccountSecurityFailure(
		ctx,
		userAccountEventStream,
		message.ID,
		durableFieldValue(message.Fields, "eventId"),
		errorClass,
		err,
	)
	if recordErr != nil {
		held, heldErr := consumer.failures.IsAccountSecurityDeadLettered(
			ctx,
			userAccountEventStream,
			message.ID,
		)
		if heldErr == nil && held {
			accountSecurityConsumerTotal.WithLabelValues(
				eventClass,
				"held_for_recovery",
			).Inc()
			return nil
		}
		return fmt.Errorf("record realtime account security failure: %w", recordErr)
	}
	if attempts < consumer.config.MaxAttempts {
		accountSecurityConsumerTotal.WithLabelValues(eventClass, "retry").Inc()
		return fmt.Errorf(
			"realtime account security attempt %d/%d failed: %w",
			attempts,
			consumer.config.MaxAttempts,
			err,
		)
	}
	if _, dlqErr := consumer.transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: userAccountSecurityDeadLetterStream,
			Fields: accountSecurityDeadLetterFields(
				message,
				err,
				attempts,
				errorClass,
			),
		},
	); dlqErr != nil {
		return fmt.Errorf("append realtime account security DLQ: %w", dlqErr)
	}
	if retentionErr := consumer.transport.SetDurableRetention(
		ctx,
		userAccountSecurityDeadLetterStream,
		accountSecurityDeadLetterRetention,
	); retentionErr != nil {
		return fmt.Errorf(
			"set realtime account security DLQ retention: %w",
			retentionErr,
		)
	}
	if markErr := consumer.failures.MarkAccountSecurityDeadLettered(
		ctx,
		userAccountEventStream,
		message.ID,
	); markErr != nil {
		return fmt.Errorf("mark realtime account security DLQ state: %w", markErr)
	}
	accountSecurityConsumerTotal.WithLabelValues(eventClass, "dlq").Inc()
	consumer.logger.ErrorContext(
		ctx,
		"realtime account security event moved to DLQ",
		slog.String("errorDigest", application.ErrorDigest(err)),
		slog.Int64("attempts", attempts),
		slog.String("eventClass", eventClass),
	)
	return nil
}

func (consumer *UserAccountSecurityConsumer) ackAndClear(
	ctx context.Context,
	messageID string,
) error {
	if err := consumer.transport.AckDurable(
		ctx,
		userAccountEventStream,
		userAccountSecurityConsumerGroup,
		messageID,
	); err != nil {
		return fmt.Errorf("ack realtime account security event: %w", err)
	}
	if err := consumer.failures.ClearAccountSecurityFailure(
		ctx,
		userAccountEventStream,
		messageID,
	); err != nil {
		return fmt.Errorf("clear realtime account security failure: %w", err)
	}
	return nil
}

func accountSecurityErrorClass(err error) string {
	switch {
	case errors.Is(err, application.ErrAccountSecurityUnavailable):
		return "dependency_unavailable"
	case errors.Is(err, application.ErrAccountSecurityDenied):
		return "state_rejected"
	default:
		return "apply_failed"
	}
}

func uniqueAccountSecurityMessages(
	groups ...[]runtimemessaging.StreamDelivery,
) []runtimemessaging.StreamDelivery {
	seen := make(map[string]struct{})
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, group := range groups {
		for _, message := range group {
			if _, duplicate := seen[message.ID]; duplicate {
				continue
			}
			seen[message.ID] = struct{}{}
			result = append(result, message)
		}
	}
	return result
}

func (consumer *UserAccountSecurityConsumer) recordSuccess() {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailure = ""
}

func (consumer *UserAccountSecurityConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailure = application.ErrorDigest(err)
}
