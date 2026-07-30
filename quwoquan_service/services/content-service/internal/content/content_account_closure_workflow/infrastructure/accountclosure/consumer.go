package accountclosure

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"sync"
	"time"

	"quwoquan_service/runtime/accountrestriction"
	rtredis "quwoquan_service/runtime/redis"
	accountclosureapp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/application"
)

const (
	defaultBatchSize    int64 = 20
	defaultMaxAttempts  int64 = 5
	defaultMinIdle            = 30 * time.Second
	defaultPollInterval       = 500 * time.Millisecond
	DeadLetterRetention       = 7 * 24 * time.Hour
)

type ApplyResult struct {
	Replayed bool
}

type EventProcessor interface {
	Apply(
		ctx context.Context,
		event UserAccountClosedEvent,
	) (ApplyResult, error)
}

// AccountRestrictionProjection owns the reversible resource restriction for
// UserSuspended/UserRestored. It is deliberately separate from EventProcessor:
// account closure is irreversible cleanup, while suspension must preserve the
// underlying aggregate state for a later restoration.
type AccountRestrictionProjection = accountclosureapp.AccountRestrictionProjection

type FailureStore interface {
	RecordFailure(
		ctx context.Context,
		stream string,
		messageID string,
		eventID string,
		cause error,
	) (int64, error)
	ClearFailure(
		ctx context.Context,
		stream string,
		messageID string,
	) error
	IsDeadLettered(
		ctx context.Context,
		stream string,
		messageID string,
	) (bool, error)
	MarkDeadLettered(
		ctx context.Context,
		stream string,
		messageID string,
	) error
}

type ConsumerConfig struct {
	BatchSize    int64
	MaxAttempts  int64
	MinIdle      time.Duration
	PollInterval time.Duration
}

func (config ConsumerConfig) withDefaults() ConsumerConfig {
	if config.BatchSize <= 0 {
		config.BatchSize = defaultBatchSize
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = defaultMaxAttempts
	}
	if config.MinIdle < 0 {
		config.MinIdle = defaultMinIdle
	}
	if config.MinIdle == 0 {
		// 零值仅用于确定性 local_contract；生产装配显式使用默认配置。
		config.MinIdle = 0
	}
	if config.PollInterval <= 0 {
		config.PollInterval = defaultPollInterval
	}
	return config
}

func DefaultConsumerConfig() ConsumerConfig {
	return ConsumerConfig{
		BatchSize:    defaultBatchSize,
		MaxAttempts:  defaultMaxAttempts,
		MinIdle:      defaultMinIdle,
		PollInterval: defaultPollInterval,
	}
}

type Consumer struct {
	redis        rtredis.Client
	processor    EventProcessor
	failures     FailureStore
	consumer     string
	config       ConsumerConfig
	logger       *slog.Logger
	restrictions AccountRestrictionProjection

	mu                sync.RWMutex
	lastSuccess       time.Time
	lastFailureDigest string
}

// WithAccountRestrictionProjection binds the mandatory production projection
// for UserSuspended/UserRestored. A restriction event received without this
// binding fails into the normal bounded retry/DLQ path instead of being ACKed.
func (consumer *Consumer) WithAccountRestrictionProjection(
	projection AccountRestrictionProjection,
) *Consumer {
	if consumer != nil {
		consumer.restrictions = projection
	}
	return consumer
}

func NewConsumer(
	redis rtredis.Client,
	processor EventProcessor,
	failures FailureStore,
	consumer string,
	logger *slog.Logger,
	config ConsumerConfig,
) (*Consumer, error) {
	if redis == nil || processor == nil || failures == nil {
		return nil, errors.New(
			"UserAccountClosed consumer requires redis, processor, and failure store",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New(
			"UserAccountClosed consumer name is required",
		)
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Consumer{
		redis:     redis,
		processor: processor,
		failures:  failures,
		consumer:  consumer,
		config:    config.withDefaults(),
		logger:    logger,
	}, nil
}

func (consumer *Consumer) EnsureGroup(ctx context.Context) error {
	if consumer == nil || consumer.redis == nil {
		return errors.New("UserAccountClosed consumer is not configured")
	}
	if err := consumer.redis.XGroupCreateMkStream(
		ctx,
		UserAccountEventStream,
		ConsumerGroup,
		"0",
	); err != nil {
		return fmt.Errorf("ensure UserAccountClosed consumer group: %w", err)
	}
	return nil
}

func (consumer *Consumer) ProcessOnce(
	ctx context.Context,
) (int, error) {
	if consumer == nil ||
		consumer.redis == nil ||
		consumer.processor == nil ||
		consumer.failures == nil {
		return 0, errors.New("UserAccountClosed consumer is not configured")
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.redis.XAutoClaim(
		ctx,
		UserAccountEventStream,
		ConsumerGroup,
		consumer.consumer,
		consumer.config.MinIdle,
		"0-0",
		consumer.config.BatchSize,
	)
	if err != nil {
		err = fmt.Errorf("auto-claim UserAccountClosed events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}
	fresh, err := consumer.redis.XReadGroup(
		ctx,
		ConsumerGroup,
		consumer.consumer,
		map[string]string{UserAccountEventStream: ">"},
		consumer.config.BatchSize,
		100*time.Millisecond,
	)
	if err != nil {
		err = fmt.Errorf("read UserAccountClosed events: %w", err)
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

func (consumer *Consumer) processMessage(
	ctx context.Context,
	message rtredis.StreamMessage,
) error {
	deadLettered, stateErr := consumer.failures.IsDeadLettered(
		ctx,
		UserAccountEventStream,
		message.ID,
	)
	if stateErr != nil {
		return fmt.Errorf(
			"read UserAccountClosed dead-letter state: %w",
			stateErr,
		)
	}
	if deadLettered {
		// DLQ only stores a sanitized source reference. Keep the original
		// payload in the source PEL until an operator explicitly releases the
		// marker through RecoverDeadLetter.
		accountClosureConsumerTotal.WithLabelValues("held_for_recovery").Inc()
		return nil
	}

	startedAt := time.Now()
	eventName := strings.TrimSpace(message.Values["eventName"])
	if eventName != UserAccountClosedName &&
		eventName != accountrestriction.UserSuspendedEventName &&
		eventName != accountrestriction.UserRestoredEventName {
		if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		accountClosureConsumerTotal.WithLabelValues("ignored").Inc()
		return nil
	}

	var replayed bool
	var err error
	if eventName == UserAccountClosedName {
		var event UserAccountClosedEvent
		event, err = DecodeUserAccountClosedEvent(message)
		if err == nil {
			var result ApplyResult
			result, err = consumer.processor.Apply(ctx, event)
			replayed = result.Replayed
		}
	} else {
		var event accountrestriction.Event
		event, err = accountrestriction.Decode(message.Values)
		if err == nil && consumer.restrictions == nil {
			err = errors.New(
				"content user account restriction projection is not configured",
			)
		}
		if err == nil {
			var result accountclosureapp.UserAccountRestrictionProjectionResult
			result, err = consumer.restrictions.Apply(ctx, event)
			replayed = result.Replayed
		}
	}
	if err == nil {
		if ackErr := consumer.ackAndClear(ctx, message.ID); ackErr != nil {
			return ackErr
		}
		outcome := "applied"
		if eventName != UserAccountClosedName {
			outcome = "restriction_applied"
		}
		if replayed {
			outcome = "replayed"
			if eventName != UserAccountClosedName {
				outcome = "restriction_replayed"
			}
		}
		accountClosureConsumerTotal.WithLabelValues(outcome).Inc()
		accountClosureDuration.Observe(time.Since(startedAt).Seconds())
		return nil
	}

	attempts, recordErr := consumer.failures.RecordFailure(
		ctx,
		UserAccountEventStream,
		message.ID,
		message.Values["eventId"],
		err,
	)
	if recordErr != nil {
		held, heldErr := consumer.failures.IsDeadLettered(
			ctx,
			UserAccountEventStream,
			message.ID,
		)
		if heldErr == nil && held {
			accountClosureConsumerTotal.WithLabelValues("held_for_recovery").Inc()
			return nil
		}
		return fmt.Errorf("record UserAccountClosed failure: %w", recordErr)
	}
	if attempts < consumer.config.MaxAttempts {
		accountClosureConsumerTotal.WithLabelValues("retry").Inc()
		return fmt.Errorf(
			"UserAccountClosed attempt %d/%d failed: %w",
			attempts,
			consumer.config.MaxAttempts,
			err,
		)
	}
	if _, dlqErr := consumer.redis.XAdd(
		ctx,
		DeadLetterStream,
		deadLetterValues(message, err, attempts),
	); dlqErr != nil {
		return fmt.Errorf("append UserAccountClosed DLQ: %w", dlqErr)
	}
	if expireErr := consumer.redis.Expire(
		ctx,
		DeadLetterStream,
		DeadLetterRetention,
	); expireErr != nil {
		return fmt.Errorf("set UserAccountClosed DLQ retention: %w", expireErr)
	}
	if markErr := consumer.failures.MarkDeadLettered(
		ctx,
		UserAccountEventStream,
		message.ID,
	); markErr != nil {
		return fmt.Errorf("mark UserAccountClosed dead-letter state: %w", markErr)
	}
	accountClosureConsumerTotal.WithLabelValues("dlq").Inc()
	consumer.logger.ErrorContext(
		ctx,
		"UserAccountClosed event moved to DLQ",
		slog.String("streamId", message.ID),
		slog.String("errorDigest", irreversibleDigest(err.Error())),
		slog.Int64("attempts", attempts),
	)
	return nil
}

// RecoverDeadLetter releases a source PEL message for another bounded retry
// cycle. It never reconstructs an event from the sanitized DLQ; the source
// stream remains the sole holder of the original payload.
func (consumer *Consumer) RecoverDeadLetter(
	ctx context.Context,
	sourceStreamID string,
) error {
	if consumer == nil || consumer.failures == nil {
		return errors.New("UserAccountClosed consumer is not configured")
	}
	sourceStreamID = strings.TrimSpace(sourceStreamID)
	if sourceStreamID == "" {
		return errors.New(
			"UserAccountClosed dead-letter source stream ID is required",
		)
	}
	deadLettered, err := consumer.failures.IsDeadLettered(
		ctx,
		UserAccountEventStream,
		sourceStreamID,
	)
	if err != nil {
		return fmt.Errorf(
			"verify UserAccountClosed dead-letter state before recovery: %w",
			err,
		)
	}
	if !deadLettered {
		// Repeated recovery is an idempotent no-op. A non-terminal retry
		// receipt must never be cleared through the operator DLQ endpoint.
		return nil
	}
	if err := consumer.failures.ClearFailure(
		ctx,
		UserAccountEventStream,
		sourceStreamID,
	); err != nil {
		return fmt.Errorf(
			"release UserAccountClosed dead-letter state: %w",
			err,
		)
	}
	return nil
}

func (consumer *Consumer) ackAndClear(
	ctx context.Context,
	messageID string,
) error {
	if err := consumer.failures.ClearFailure(
		ctx,
		UserAccountEventStream,
		messageID,
	); err != nil {
		return fmt.Errorf("clear UserAccountClosed failure state: %w", err)
	}
	if err := consumer.redis.XAck(
		ctx,
		UserAccountEventStream,
		ConsumerGroup,
		messageID,
	); err != nil {
		return fmt.Errorf("ack UserAccountClosed event: %w", err)
	}
	return nil
}

func (consumer *Consumer) Run(ctx context.Context) {
	ticker := time.NewTicker(consumer.config.PollInterval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil &&
			ctx.Err() == nil {
			consumer.logger.ErrorContext(
				ctx,
				"UserAccountClosed consumer scan failed",
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

func (consumer *Consumer) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return errors.New(
			"UserAccountClosed consumer has not completed a scan",
		)
	}
	if consumer.lastFailureDigest != "" {
		return fmt.Errorf(
			"UserAccountClosed consumer last scan failed (digest=%s)",
			consumer.lastFailureDigest,
		)
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New("UserAccountClosed consumer heartbeat is stale")
	}
	return nil
}

func (consumer *Consumer) recordSuccess() {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailureDigest = ""
}

func (consumer *Consumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailureDigest = irreversibleDigest(err.Error())
}

func uniqueMessages(
	groups ...[]rtredis.StreamMessage,
) []rtredis.StreamMessage {
	seen := map[string]struct{}{}
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

func deadLetterValues(
	message rtredis.StreamMessage,
	cause error,
	attempts int64,
) map[string]string {
	eventName := strings.TrimSpace(message.Values["eventName"])
	if eventName == "" {
		eventName = "unknown"
	}
	return map[string]string{
		"deadLetterId":   failureID(UserAccountEventStream, message.ID),
		"sourceStream":   UserAccountEventStream,
		"sourceStreamId": message.ID,
		"eventName":      eventName,
		"eventIdDigest":  irreversibleDigest(message.Values["eventId"]),
		"payloadDigest":  irreversibleDigest(message.Values["payload"]),
		"attempts":       strconv.FormatInt(attempts, 10),
		"errorDigest":    irreversibleDigest(cause.Error()),
		"deadLetteredAt": time.Now().UTC().Format(time.RFC3339Nano),
	}
}
