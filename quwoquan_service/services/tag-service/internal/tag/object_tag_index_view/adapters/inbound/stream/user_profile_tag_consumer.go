package stream

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
	ports "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/domain/ports"
)

const (
	UserAccountEventStream               = "events.user.account"
	UserProfileTagConsumerGroup          = "tag-service-user-profile-tags"
	UserProfileTagDeadLetterStream       = "events.user.account.tag-service.dlq"
	userProfileTagsChangedEvent          = "UserProfileTagsChanged"
	userProfileTagConsumerBatch    int64 = 50
	userProfileTagMinIdle                = 30 * time.Second
	userProfileTagPoll                   = 250 * time.Millisecond
	userProfileTagDLQRetention           = 30 * 24 * time.Hour
)

var errUnsupportedUserAccountEvent = errors.New("unsupported user account event")

type UserProfileTagTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

type UserProfileTagConsumer struct {
	transport  UserProfileTagTransport
	projector  ports.UserProfileTagProjector
	consumerID string
	logger     *slog.Logger

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewUserProfileTagConsumer(
	transport UserProfileTagTransport,
	projector ports.UserProfileTagProjector,
	consumerID string,
	logger *slog.Logger,
) (*UserProfileTagConsumer, error) {
	if transport == nil || projector == nil {
		return nil, errors.New(
			"user profile tag consumer requires transport and projector",
		)
	}
	consumerID = strings.TrimSpace(consumerID)
	if consumerID == "" {
		return nil, errors.New("user profile tag consumer ID is required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &UserProfileTagConsumer{
		transport:  transport,
		projector:  projector,
		consumerID: consumerID,
		logger:     logger,
	}, nil
}

func (consumer *UserProfileTagConsumer) EnsureGroup(ctx context.Context) error {
	if consumer == nil || consumer.transport == nil {
		return errors.New("user profile tag consumer is unavailable")
	}
	return consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		UserAccountEventStream,
		UserProfileTagConsumerGroup,
		"0",
	)
}

func (consumer *UserProfileTagConsumer) ProcessOnce(
	ctx context.Context,
) (int, error) {
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordFailure(err)
		return 0, err
	}
	claimed, _, err := consumer.transport.ReclaimDurable(
		ctx,
		UserAccountEventStream,
		UserProfileTagConsumerGroup,
		consumer.consumerID,
		userProfileTagMinIdle,
		"0-0",
		userProfileTagConsumerBatch,
	)
	if err != nil {
		consumer.recordFailure(err)
		return 0, fmt.Errorf("reclaim user profile tag events: %w", err)
	}
	fresh, err := consumer.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   UserAccountEventStream,
			Group:    UserProfileTagConsumerGroup,
			Consumer: consumer.consumerID,
			Count:    userProfileTagConsumerBatch,
			Block:    100 * time.Millisecond,
		},
	)
	if err != nil {
		consumer.recordFailure(err)
		return 0, fmt.Errorf("read user profile tag events: %w", err)
	}
	processed := 0
	var firstErr error
	for _, message := range uniqueProfileTagDeliveries(claimed, fresh) {
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

func (consumer *UserProfileTagConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(userProfileTagPoll)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(
				ctx,
				"user profile tag projection consume failed",
				slog.String("error_type", fmt.Sprintf("%T", err)),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *UserProfileTagConsumer) Healthy(maxStaleness time.Duration) error {
	if consumer == nil {
		return errors.New("user profile tag consumer is unavailable")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.mu.RLock()
	defer consumer.mu.RUnlock()
	if consumer.lastSuccess.IsZero() {
		return errors.New("user profile tag consumer has not completed a scan")
	}
	if consumer.lastFailure != nil {
		return fmt.Errorf(
			"user profile tag consumer last scan failed: %w",
			consumer.lastFailure,
		)
	}
	if time.Since(consumer.lastSuccess) > maxStaleness {
		return errors.New("user profile tag consumer heartbeat is stale")
	}
	return nil
}

func (consumer *UserProfileTagConsumer) processMessage(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
) error {
	fields := profileTagFieldValues(message.Fields)
	projection, err := decodeUserProfileTagProjection(fields)
	if errors.Is(err, errUnsupportedUserAccountEvent) {
		return consumer.ack(ctx, message.ID)
	}
	if err != nil {
		return consumer.deadLetterMalformed(
			ctx,
			message,
			fields["eventId"],
			err,
		)
	}
	if _, err := consumer.projector.ApplyUserProfileTagProjection(
		ctx,
		projection,
	); err != nil {
		// 存储故障属于可恢复依赖错误：保留 source PEL 等待 reclaim，
		// 不把暂态错误错误隔离为永久坏消息。
		return fmt.Errorf("apply user profile tag projection: %w", err)
	}
	return consumer.ack(ctx, message.ID)
}

func (consumer *UserProfileTagConsumer) deadLetterMalformed(
	ctx context.Context,
	message runtimemessaging.StreamDelivery,
	eventID string,
	cause error,
) error {
	if _, dlqErr := consumer.transport.PublishDeadLetter(
		ctx,
		runtimemessaging.DeadLetterMessage{
			SourceStream:      UserAccountEventStream,
			DestinationStream: UserProfileTagDeadLetterStream,
			SourceID:          message.ID,
			Reason:            "profile_tag_projection_failed",
			Fields: []runtimemessaging.DurableField{
				{Name: "sourceMessageId", Value: message.ID},
				{
					Name:  "eventDigest",
					Value: profileTagDigest(eventID),
				},
				{Name: "errorDigest", Value: profileTagDigest(cause.Error())},
			},
		},
	); dlqErr != nil {
		return fmt.Errorf("publish user profile tag projection DLQ: %w", dlqErr)
	}
	if retentionErr := consumer.transport.SetDurableRetention(
		ctx,
		UserProfileTagDeadLetterStream,
		userProfileTagDLQRetention,
	); retentionErr != nil {
		return fmt.Errorf(
			"set user profile tag projection DLQ retention: %w",
			retentionErr,
		)
	}
	return consumer.ack(ctx, message.ID)
}

func (consumer *UserProfileTagConsumer) ack(
	ctx context.Context,
	messageID string,
) error {
	if err := consumer.transport.AckDurable(
		ctx,
		UserAccountEventStream,
		UserProfileTagConsumerGroup,
		messageID,
	); err != nil {
		return fmt.Errorf("ack user profile tag event: %w", err)
	}
	return nil
}

func decodeUserProfileTagProjection(
	fields map[string]string,
) (ports.UserProfileTagProjection, error) {
	if strings.TrimSpace(fields["eventName"]) != userProfileTagsChangedEvent {
		return ports.UserProfileTagProjection{}, errUnsupportedUserAccountEvent
	}
	eventID := strings.TrimSpace(fields["eventId"])
	accountID := strings.TrimSpace(fields["accountId"])
	version, err := strconv.ParseInt(
		strings.TrimSpace(fields["accountVersion"]),
		10,
		64,
	)
	if eventID == "" || accountID == "" || err != nil || version <= 0 {
		return ports.UserProfileTagProjection{}, errors.New(
			"invalid user profile tag event envelope",
		)
	}
	var payload struct {
		UserID            string    `json:"userId"`
		TagRefs           []string  `json:"tagRefs"`
		TaxonomyReleaseID string    `json:"taxonomyReleaseId"`
		ProfileVersion    int64     `json:"profileVersion"`
		OccurredAt        time.Time `json:"occurredAt"`
	}
	decoder := json.NewDecoder(bytes.NewBufferString(fields["payload"]))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return ports.UserProfileTagProjection{}, fmt.Errorf(
			"decode user profile tag event payload: %w",
			err,
		)
	}
	if err := requireProfileTagJSONEOF(decoder); err != nil {
		return ports.UserProfileTagProjection{}, err
	}
	payload.UserID = strings.TrimSpace(payload.UserID)
	payload.TaxonomyReleaseID = strings.TrimSpace(payload.TaxonomyReleaseID)
	if payload.UserID != accountID ||
		payload.TaxonomyReleaseID == "" ||
		payload.ProfileVersion != version ||
		payload.OccurredAt.IsZero() {
		return ports.UserProfileTagProjection{}, errors.New(
			"invalid user profile tag event payload",
		)
	}
	tagRefs, err := normalizeProfileTagRefs(payload.TagRefs)
	if err != nil {
		return ports.UserProfileTagProjection{}, err
	}
	return ports.UserProfileTagProjection{
		EventID:           eventID,
		UserID:            payload.UserID,
		TagRefs:           tagRefs,
		TaxonomyReleaseID: payload.TaxonomyReleaseID,
		ProfileVersion:    payload.ProfileVersion,
		OccurredAt:        payload.OccurredAt.UTC(),
	}, nil
}

func normalizeProfileTagRefs(values []string) ([]string, error) {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		tagRef := strings.TrimSpace(value)
		if !strings.HasPrefix(tagRef, "Audience/用户/职业/") &&
			!strings.HasPrefix(tagRef, "Audience/用户/兴趣偏好/") {
			return nil, errors.New("user profile tag projection contains invalid tagRef")
		}
		if _, exists := seen[tagRef]; exists {
			continue
		}
		seen[tagRef] = struct{}{}
		result = append(result, tagRef)
	}
	return result, nil
}

func requireProfileTagJSONEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); errors.Is(err, io.EOF) {
		return nil
	} else if err != nil {
		return fmt.Errorf("decode user profile tag trailing payload: %w", err)
	}
	return errors.New("user profile tag event payload contains trailing JSON")
}

func profileTagFieldValues(
	fields []runtimemessaging.DurableField,
) map[string]string {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[field.Name] = field.Value
	}
	return values
}

func uniqueProfileTagDeliveries(
	groups ...[]runtimemessaging.StreamDelivery,
) []runtimemessaging.StreamDelivery {
	seen := map[string]struct{}{}
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

func profileTagDigest(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}

func (consumer *UserProfileTagConsumer) recordSuccess() {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastSuccess = time.Now().UTC()
	consumer.lastFailure = nil
}

func (consumer *UserProfileTagConsumer) recordFailure(err error) {
	consumer.mu.Lock()
	defer consumer.mu.Unlock()
	consumer.lastFailure = err
}
