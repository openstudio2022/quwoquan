package mq

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"quwoquan_service/runtime/accountrestriction"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

const (
	UserAccountEventStream                       = "events.user.account"
	UserAccountRestrictionConsumerGroup          = "search-service-search-index-restrictions"
	UserAccountRestrictionDeadLetterStream       = "events.user.account.search-index-restrictions.dlq"
	userAccountRestrictionBatch            int64 = 50
	userAccountRestrictionMinIdle                = 30 * time.Second
	userAccountRestrictionPoll                   = 250 * time.Millisecond
	userAccountRestrictionDLQRetention           = 7 * 24 * time.Hour
)

type UserAccountRestrictionTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

// UserAccountRestrictionConsumer is the SearchIndexView-owned durable entry
// point for reversible UserSuspended/UserRestored projections. Account closure
// belongs to SearchRequestFact and is acknowledged as an unrelated stream
// event by this independent consumer group.
type UserAccountRestrictionConsumer struct {
	transport  UserAccountRestrictionTransport
	projection application.UserAccountRestrictionProjection
	consumer   string
	logger     *slog.Logger

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure string
}

func NewUserAccountRestrictionConsumer(
	transport UserAccountRestrictionTransport,
	projection application.UserAccountRestrictionProjection,
	consumer string,
	logger *slog.Logger,
) (*UserAccountRestrictionConsumer, error) {
	if transport == nil || projection == nil {
		return nil, errors.New(
			"search account restriction consumer requires transport and projection",
		)
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New("search account restriction consumer identity is required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &UserAccountRestrictionConsumer{
		transport: transport, projection: projection, consumer: consumer, logger: logger,
	}, nil
}

func (consumer *UserAccountRestrictionConsumer) EnsureGroup(ctx context.Context) error {
	if consumer == nil || consumer.transport == nil {
		return errors.New("search account restriction consumer is not configured")
	}
	return consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		UserAccountEventStream,
		UserAccountRestrictionConsumerGroup,
		"0",
	)
}

func (consumer *UserAccountRestrictionConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if consumer == nil || consumer.transport == nil || consumer.projection == nil {
		return 0, errors.New("search account restriction consumer is not configured")
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.transport.ReclaimDurable(
		ctx,
		UserAccountEventStream,
		UserAccountRestrictionConsumerGroup,
		consumer.consumer,
		userAccountRestrictionMinIdle,
		"0-0",
		userAccountRestrictionBatch,
	)
	if err != nil {
		err = fmt.Errorf("reclaim search account restriction events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}
	fresh, err := consumer.transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream:   UserAccountEventStream,
		Group:    UserAccountRestrictionConsumerGroup,
		Consumer: consumer.consumer,
		Count:    userAccountRestrictionBatch,
		Block:    100 * time.Millisecond,
	})
	if err != nil {
		err = fmt.Errorf("read search account restriction events: %w", err)
		consumer.recordFailure(err)
		return 0, err
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueRestrictionMessages(claimed, fresh) {
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

func (consumer *UserAccountRestrictionConsumer) processMessage(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
) error {
	values := restrictionFieldValues(message.Fields)
	event, err := accountrestriction.Decode(values)
	if errors.Is(err, accountrestriction.ErrUnsupportedEvent) {
		return consumer.transport.AckDurable(
			ctx, UserAccountEventStream, UserAccountRestrictionConsumerGroup, message.ID,
		)
	}
	if err != nil {
		if _, publishErr := consumer.transport.PublishDeadLetter(
			ctx,
			runtimemessaging.DeadLetterMessage{
				SourceStream:      UserAccountEventStream,
				DestinationStream: UserAccountRestrictionDeadLetterStream,
				SourceID:          message.ID,
				Reason:            "invalid_account_restriction_event",
				Fields: []runtimemessaging.DurableField{
					{Name: "sourceMessageId", Value: message.ID},
					{Name: "eventDigest", Value: restrictionDigest(values["eventId"])},
					{Name: "errorDigest", Value: restrictionDigest(err.Error())},
				},
			},
		); publishErr != nil {
			return errors.Join(err, publishErr)
		}
		if retentionErr := consumer.transport.SetDurableRetention(
			ctx,
			UserAccountRestrictionDeadLetterStream,
			userAccountRestrictionDLQRetention,
		); retentionErr != nil {
			return errors.Join(err, retentionErr)
		}
		return consumer.transport.AckDurable(
			ctx, UserAccountEventStream, UserAccountRestrictionConsumerGroup, message.ID,
		)
	}
	if _, err := consumer.projection.Apply(ctx, event); err != nil {
		// Provider/store failures stay pending for durable reclaim. They are not
		// converted into an irreversible contract error.
		return fmt.Errorf("apply search account restriction projection: %w", err)
	}
	return consumer.transport.AckDurable(
		ctx, UserAccountEventStream, UserAccountRestrictionConsumerGroup, message.ID,
	)
}

func (consumer *UserAccountRestrictionConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(userAccountRestrictionPoll)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(
				ctx,
				"search account restriction consume failed",
				slog.String("errorDigest", restrictionDigest(err.Error())),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *UserAccountRestrictionConsumer) Healthy(maxStaleness time.Duration) error {
	if consumer == nil {
		return errors.New("search account restriction consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return errors.New("search account restriction consumer has not completed a scan")
	}
	if consumer.lastFailure != "" {
		return fmt.Errorf(
			"search account restriction consumer last scan failed (digest=%s)",
			consumer.lastFailure,
		)
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New("search account restriction consumer heartbeat is stale")
	}
	return nil
}

func uniqueRestrictionMessages(
	groups ...[]runtimemessaging.StreamDelivery,
) []runtimemessaging.StreamDelivery {
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

func restrictionFieldValues(fields []runtimemessaging.DurableField) map[string]string {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[field.Name] = strings.TrimSpace(field.Value)
	}
	return values
}

func restrictionDigest(value string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(digest[:])
}

func (consumer *UserAccountRestrictionConsumer) recordSuccess() {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailure = ""
}

func (consumer *UserAccountRestrictionConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailure = restrictionDigest(err.Error())
}
