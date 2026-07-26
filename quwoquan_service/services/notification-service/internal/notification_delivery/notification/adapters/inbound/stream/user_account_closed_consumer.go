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

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
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
	transport  DurableMessageTransport
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
	transport DurableMessageTransport,
	projection application.UserAccountClosedProjection,
	failures UserAccountClosedFailureStore,
	consumer string,
	logger *slog.Logger,
	config UserAccountClosedConsumerConfig,
) (*UserAccountClosedConsumer, error) {
	if transport == nil || projection == nil || failures == nil {
		return nil, errors.New(
			"notification UserAccountClosed consumer requires message transport, projection, and failure store",
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
		return errors.New(
			"notification UserAccountClosed consumer is not configured",
		)
	}
	if err := consumer.transport.EnsureDurableConsumerGroup(
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
		consumer.transport == nil ||
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
		err = fmt.Errorf(
			"auto-claim notification UserAccountClosed events: %w",
			err,
		)
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
	if consumer.lastFailureDigest != "" {
		return fmt.Errorf(
			"notification UserAccountClosed consumer last scan failed (digest=%s)",
			consumer.lastFailureDigest,
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
			"read notification UserAccountClosed dead-letter state: %w",
			stateErr,
		)
	}
	if deadLettered {
		// DLQ 仅保存 source PEL 引用；保持该消息未 ACK，直到受控恢复释放
		// dead-letter 标记后由 source stream 重新读取原始 payload。
		userAccountClosedConsumerTotal.WithLabelValues("held_for_recovery").Inc()
		return nil
	}
	event, err := decodeNotificationUserAccountClosed(message)
	if errors.Is(err, errUnsupportedUserAccountEvent) {
		if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		userAccountClosedConsumerTotal.WithLabelValues("ignored").Inc()
		return nil
	}
	errorClass := "invalid_event"
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
		errorClass = userAccountClosedProjectionErrorClass(err)
	}

	attempts, recordErr := consumer.failures.RecordUserAccountClosedFailure(
		ctx,
		UserAccountEventStream,
		message.ID,
		durableFieldValue(message.Fields, "eventId"),
		errorClass,
		err,
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
	if _, dlqErr := consumer.transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: UserAccountClosedDeadLetterStream,
			Fields: userAccountClosedDeadLetterFields(
				message,
				err,
				attempts,
				errorClass,
			),
		},
	); dlqErr != nil {
		return fmt.Errorf(
			"append notification UserAccountClosed DLQ: %w",
			dlqErr,
		)
	}
	if expireErr := consumer.transport.SetDurableRetention(
		ctx,
		UserAccountClosedDeadLetterStream,
		userAccountClosedDeadLetterTimeout,
	); expireErr != nil {
		return fmt.Errorf(
			"set notification UserAccountClosed DLQ retention: %w",
			expireErr,
		)
	}
	if markErr := consumer.failures.MarkUserAccountClosedDeadLettered(
		ctx,
		UserAccountEventStream,
		message.ID,
	); markErr != nil {
		return fmt.Errorf(
			"mark notification UserAccountClosed dead-letter state: %w",
			markErr,
		)
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

// RecoverDeadLetter releases a source PEL for one more bounded retry cycle.
// It never reconstructs a message from the DLQ: the source message remains unacknowledged
// and the next consumer scan reclaims its original payload from UserAccountEventStream.
func (consumer *UserAccountClosedConsumer) RecoverDeadLetter(
	ctx context.Context,
	sourceStreamID string,
) error {
	if consumer == nil || consumer.failures == nil {
		return errors.New("notification UserAccountClosed consumer is not configured")
	}
	sourceStreamID = strings.TrimSpace(sourceStreamID)
	if sourceStreamID == "" {
		return errors.New(
			"notification UserAccountClosed dead-letter source stream ID is required",
		)
	}
	deadLettered, err := consumer.failures.IsUserAccountClosedDeadLettered(
		ctx,
		UserAccountEventStream,
		sourceStreamID,
	)
	if err != nil {
		return fmt.Errorf(
			"verify notification UserAccountClosed dead-letter state before recovery: %w",
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
			"release notification UserAccountClosed dead-letter state: %w",
			err,
		)
	}
	return nil
}

func (consumer *UserAccountClosedConsumer) ackAndClear(
	ctx context.Context,
	messageID string,
) error {
	if err := consumer.transport.AckDurable(
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

func userAccountClosedProjectionErrorClass(cause error) string {
	if errors.Is(cause, application.ErrUserAccountClosedEventIDConflict) {
		return "identity_conflict"
	}
	return "projection_failed"
}

func uniqueUserAccountClosedMessages(
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
