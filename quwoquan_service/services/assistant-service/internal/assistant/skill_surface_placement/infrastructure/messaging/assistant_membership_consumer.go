package messaging

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	placementapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
)

const (
	AssistantMembershipStream        = "events.chat.assistant_memberships"
	AssistantMembershipDeadLetter    = "events.chat.assistant_memberships.dlq"
	AssistantMembershipConsumerGroup = "assistant-service-surface-placement"
	assistantMembershipDedupTTL      = 24 * time.Hour
	assistantMembershipDLQTTL        = 7 * 24 * time.Hour
)

type AssistantMembershipProjector interface {
	Apply(context.Context, placementapplication.AssistantMembershipChange) error
}

type AssistantMembershipConsumer struct {
	transport runtimemessaging.DurableDeliveryTransport
	projector AssistantMembershipProjector
	consumer  string
	logger    *slog.Logger
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulPoll time.Time
	lastFailure        error
}

func NewAssistantMembershipConsumer(
	transport runtimemessaging.DurableDeliveryTransport,
	projector AssistantMembershipProjector,
	consumer string,
	logger *slog.Logger,
) *AssistantMembershipConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "assistant-surface-worker"
	}
	return &AssistantMembershipConsumer{
		transport: transport,
		projector: projector,
		consumer:  consumer,
		logger:    logger,
		now:       time.Now,
	}
}

func (consumer *AssistantMembershipConsumer) EnsureGroup(ctx context.Context) error {
	if consumer == nil || consumer.transport == nil {
		return fmt.Errorf("assistant membership consumer transport not configured")
	}
	return consumer.transport.EnsureDurableConsumerGroup(
		ctx,
		AssistantMembershipStream,
		AssistantMembershipConsumerGroup,
		"0",
	)
}

func (consumer *AssistantMembershipConsumer) ProcessOnce(
	ctx context.Context,
) (processed int, resultErr error) {
	defer func() {
		consumer.recordPoll(resultErr)
	}()
	if consumer == nil || consumer.transport == nil || consumer.projector == nil {
		return 0, fmt.Errorf("assistant membership consumer not configured")
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		return 0, err
	}
	messages, err := consumer.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   AssistantMembershipStream,
			Group:    AssistantMembershipConsumerGroup,
			Consumer: consumer.consumer,
			Count:    10,
			Block:    200 * time.Millisecond,
		},
	)
	if err != nil {
		return 0, err
	}
	for _, message := range messages {
		dedupKey := assistantMembershipDedupKey(message)
		claimed, claimErr := consumer.transport.ClaimDurableDelivery(
			ctx,
			dedupKey,
			message.ID,
			assistantMembershipDedupTTL,
		)
		if claimErr != nil {
			return processed, claimErr
		}
		if !claimed {
			if ackErr := consumer.transport.AckDurable(
				ctx,
				AssistantMembershipStream,
				AssistantMembershipConsumerGroup,
				message.ID,
			); ackErr != nil {
				return processed, ackErr
			}
			processed++
			continue
		}
		if projectErr := consumer.project(message, ctx); projectErr != nil {
			_ = consumer.transport.ReleaseDurableDelivery(ctx, dedupKey)
			consumer.logger.Error(
				"assistant membership projection failed",
				"streamId", message.ID,
				"errorDigest", assistantMembershipErrorDigest(projectErr),
			)
			if _, dlqErr := consumer.transport.PublishDeadLetter(
				ctx,
				runtimemessaging.DeadLetterMessage{
					SourceStream:      AssistantMembershipStream,
					DestinationStream: AssistantMembershipDeadLetter,
					SourceID:          message.ID,
					Reason:            "projection_failed",
					Fields:            assistantMembershipDeadLetterFields(message, projectErr),
				},
			); dlqErr != nil {
				return processed, fmt.Errorf("assistant membership dlq: %w", dlqErr)
			}
			if retentionErr := consumer.transport.SetDurableRetention(
				ctx,
				AssistantMembershipDeadLetter,
				assistantMembershipDLQTTL,
			); retentionErr != nil {
				return processed, retentionErr
			}
		}
		if ackErr := consumer.transport.AckDurable(
			ctx,
			AssistantMembershipStream,
			AssistantMembershipConsumerGroup,
			message.ID,
		); ackErr != nil {
			return processed, ackErr
		}
		processed++
	}
	return processed, nil
}

func (consumer *AssistantMembershipConsumer) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if consumer == nil {
		return fmt.Errorf("assistant membership consumer is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	consumer.healthMu.RLock()
	lastSuccessfulPoll := consumer.lastSuccessfulPoll
	lastFailure := consumer.lastFailure
	consumer.healthMu.RUnlock()
	if lastFailure != nil {
		return lastFailure
	}
	if lastSuccessfulPoll.IsZero() {
		return fmt.Errorf("assistant membership consumer has not completed a poll")
	}
	if consumer.now().UTC().Sub(lastSuccessfulPoll) > maxStaleness {
		return fmt.Errorf("assistant membership consumer heartbeat is stale")
	}
	return nil
}

func (consumer *AssistantMembershipConsumer) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 500 * time.Millisecond
	}
	if err := consumer.EnsureGroup(ctx); err != nil {
		consumer.recordPoll(err)
		consumer.logger.Error("assistant membership consumer ensure group failed", "err", err)
		return
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil {
			consumer.logger.Error("assistant membership consumer tick failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (consumer *AssistantMembershipConsumer) recordPoll(err error) {
	if consumer == nil {
		return
	}
	consumer.healthMu.Lock()
	defer consumer.healthMu.Unlock()
	if err != nil {
		consumer.lastFailure = err
		return
	}
	consumer.lastSuccessfulPoll = consumer.now().UTC()
	consumer.lastFailure = nil
}

func (consumer *AssistantMembershipConsumer) project(
	message runtimemessaging.StreamDelivery,
	ctx context.Context,
) error {
	eventType := assistantMembershipField(message.Fields, "eventType")
	accountField := "invitedByAccountId"
	personaField := "invitedBy"
	if eventType == placementapplication.AssistantConversationMemberRemoved {
		accountField = "removedByAccountId"
		personaField = "removedBy"
	}
	occurredAt, err := time.Parse(
		time.RFC3339Nano,
		assistantMembershipField(message.Fields, "occurredAt"),
	)
	if err != nil {
		return fmt.Errorf("assistant membership occurredAt is invalid: %w", err)
	}
	return consumer.projector.Apply(ctx, placementapplication.AssistantMembershipChange{
		EventID:        assistantMembershipField(message.Fields, "eventId"),
		EventType:      eventType,
		ConversationID: assistantMembershipField(message.Fields, "conversationId"),
		ActorAccountID: assistantMembershipField(message.Fields, accountField),
		ActorPersonaID: assistantMembershipField(message.Fields, personaField),
		OccurredAt:     occurredAt,
	})
}

func assistantMembershipField(
	fields []runtimemessaging.DurableField,
	name string,
) string {
	for _, field := range fields {
		if field.Name == name {
			return strings.TrimSpace(field.Value)
		}
	}
	return ""
}

func assistantMembershipDedupKey(message runtimemessaging.StreamDelivery) string {
	eventID := assistantMembershipField(message.Fields, "eventId")
	if eventID == "" {
		eventID = strings.TrimSpace(message.ID)
	}
	return "assistant:skill-surface-membership:" + eventID
}

func assistantMembershipErrorDigest(err error) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(err.Error())))
	return hex.EncodeToString(sum[:])
}

func assistantMembershipDeadLetterFields(
	message runtimemessaging.StreamDelivery,
	err error,
) []runtimemessaging.DurableField {
	fields := make([]runtimemessaging.DurableField, 0, len(message.Fields)+1)
	for _, field := range message.Fields {
		if field.Name != "errorDigest" {
			fields = append(fields, field)
		}
	}
	return append(fields, runtimemessaging.DurableField{
		Name:  "errorDigest",
		Value: assistantMembershipErrorDigest(err),
	})
}
