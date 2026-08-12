package mq

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strconv"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

const (
	UserProfileSearchProjectionStream              = "events.user.profile_search"
	UserProfileSearchProjectionConsumerGroup       = "search-service-user-profile-projection"
	UserProfileSearchProjectionDeadLetter          = "events.user.profile_search.search-service.dlq"
	userProfileProjectionBatch               int64 = 50
	userProfileProjectionMinIdle                   = 30 * time.Second
	userProfileProjectionPoll                      = 250 * time.Millisecond
)

type UserProfileSearchProjectionTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

type UserProfileSearchProjectionConsumer struct {
	transport  UserProfileSearchProjectionTransport
	projection application.UserProfileSearchProjection
	consumer   string
	logger     *slog.Logger
	mu         sync.RWMutex
	lastScan   time.Time
	lastError  string
}

func NewUserProfileSearchProjectionConsumer(
	transport UserProfileSearchProjectionTransport,
	projection application.UserProfileSearchProjection,
	consumer string,
	logger *slog.Logger,
) (*UserProfileSearchProjectionConsumer, error) {
	if transport == nil || projection == nil || strings.TrimSpace(consumer) == "" {
		return nil, errors.New("Search UserProfile projection consumer requires transport, projection and identity")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &UserProfileSearchProjectionConsumer{
		transport: transport, projection: projection,
		consumer: strings.TrimSpace(consumer), logger: logger,
	}, nil
}

func (consumer *UserProfileSearchProjectionConsumer) EnsureGroup(ctx context.Context) error {
	return consumer.transport.EnsureDurableConsumerGroup(
		ctx, UserProfileSearchProjectionStream,
		UserProfileSearchProjectionConsumerGroup, "0",
	)
}

func (consumer *UserProfileSearchProjectionConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if consumer == nil || consumer.transport == nil || consumer.projection == nil {
		return 0, errors.New("Search UserProfile projection consumer is not configured")
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.transport.ReclaimDurable(
		ctx, UserProfileSearchProjectionStream,
		UserProfileSearchProjectionConsumerGroup, consumer.consumer,
		userProfileProjectionMinIdle, "0-0", userProfileProjectionBatch,
	)
	if err != nil {
		consumer.recordFailure(err)
		return 0, fmt.Errorf("reclaim Search UserProfile projection: %w", err)
	}
	fresh, err := consumer.transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream:   UserProfileSearchProjectionStream,
		Group:    UserProfileSearchProjectionConsumerGroup,
		Consumer: consumer.consumer, Count: userProfileProjectionBatch,
		Block: 100 * time.Millisecond,
	})
	if err != nil {
		consumer.recordFailure(err)
		return 0, fmt.Errorf("read Search UserProfile projection: %w", err)
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueProfileProjectionMessages(claimed, fresh) {
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

func (consumer *UserProfileSearchProjectionConsumer) processMessage(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
) error {
	fields := profileProjectionFields(message.Fields)
	event, err := decodeUserProfileSearchProjection(fields)
	if err != nil {
		if _, dlqErr := consumer.transport.PublishDeadLetter(ctx, runtimemessaging.DeadLetterMessage{
			SourceStream:      UserProfileSearchProjectionStream,
			DestinationStream: UserProfileSearchProjectionDeadLetter,
			SourceID:          message.ID, Reason: "invalid_user_profile_projection",
			Fields: []runtimemessaging.DurableField{
				{Name: "sourceMessageId", Value: message.ID},
				{Name: "eventDigest", Value: profileProjectionDigest(fields["eventId"])},
				{Name: "errorDigest", Value: profileProjectionDigest(err.Error())},
			},
		}); dlqErr != nil {
			return errors.Join(err, dlqErr)
		}
		return consumer.transport.AckDurable(
			ctx, UserProfileSearchProjectionStream,
			UserProfileSearchProjectionConsumerGroup, message.ID,
		)
	}
	if _, err := consumer.projection.Apply(ctx, event); err != nil {
		return fmt.Errorf("apply Search UserProfile projection: %w", err)
	}
	return consumer.transport.AckDurable(
		ctx, UserProfileSearchProjectionStream,
		UserProfileSearchProjectionConsumerGroup, message.ID,
	)
}

func decodeUserProfileSearchProjection(
	fields map[string]string,
) (application.UserProfileSearchProjectionEvent, error) {
	var event application.UserProfileSearchProjectionEvent
	if fields["eventName"] != "UserProfileSearchProjectionRequested" {
		return event, errors.New("unsupported UserProfile projection event")
	}
	decoder := json.NewDecoder(bytes.NewBufferString(fields["payload"]))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&event); err != nil {
		return event, errors.New("invalid UserProfile projection payload")
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return event, errors.New("invalid UserProfile projection payload suffix")
	}
	version, err := strconv.ParseInt(fields["profileVersion"], 10, 64)
	if err != nil || event.EventID != fields["eventId"] ||
		event.UserID != fields["userId"] || event.ProfileVersion != version {
		return event, errors.New("UserProfile projection envelope binding is invalid")
	}
	if err := event.Validate(); err != nil {
		return event, err
	}
	return event, nil
}

func (consumer *UserProfileSearchProjectionConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(userProfileProjectionPoll)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(ctx, "Search UserProfile projection consume failed",
				slog.String("errorDigest", profileProjectionDigest(err.Error())))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *UserProfileSearchProjectionConsumer) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastScan.IsZero() {
		return errors.New("Search UserProfile projection consumer has not completed a scan")
	}
	if consumer.lastError != "" {
		return fmt.Errorf("Search UserProfile projection consumer failed (digest=%s)", consumer.lastError)
	}
	if time.Since(consumer.lastScan) > maxStaleness {
		return errors.New("Search UserProfile projection consumer scan is stale")
	}
	return nil
}

func (consumer *UserProfileSearchProjectionConsumer) recordSuccess() {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastScan = time.Now().UTC()
	consumer.lastError = ""
}

func (consumer *UserProfileSearchProjectionConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastError = profileProjectionDigest(err.Error())
}

func profileProjectionFields(fields []runtimemessaging.DurableField) map[string]string {
	result := make(map[string]string, len(fields))
	for _, field := range fields {
		result[field.Name] = field.Value
	}
	return result
}

func uniqueProfileProjectionMessages(groups ...[]runtimemessaging.StreamDelivery) []runtimemessaging.StreamDelivery {
	seen := map[string]bool{}
	result := make([]runtimemessaging.StreamDelivery, 0)
	for _, group := range groups {
		for _, message := range group {
			if !seen[message.ID] {
				seen[message.ID] = true
				result = append(result, message)
			}
		}
	}
	return result
}

func profileProjectionDigest(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}
