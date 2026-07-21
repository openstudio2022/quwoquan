package messaging

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/assistant-service/internal/application"
)

const (
	AssistantMentionedStream         = "events.chat.assistant_mentions"
	AssistantMentionedDeadLetter     = "events.chat.assistant_mentions.dlq"
	AssistantMentionedConsumerGroup  = "assistant-service"
	assistantMentionDedupTTL         = 24 * time.Hour
	assistantMentionDeadLetterTTL    = 7 * 24 * time.Hour
	assistantMentionDeadLetterReason = "handler_failed"
)

type AssistantMentionHandler interface {
	HandleAssistantMentioned(ctx context.Context, evt application.AssistantMentionedEvent) error
}

type AssistantMentionedConsumer struct {
	transport runtimemessaging.DurableDeliveryTransport
	handler   AssistantMentionHandler
	consumer  string
	logger    *slog.Logger
}

// NewAssistantMentionedConsumerWithTransport consumes the object-owned stream
// through the preflighted runtime transport. The stream and consumer-group
// identifiers remain assistant-owned constants.
func NewAssistantMentionedConsumerWithTransport(
	transport runtimemessaging.DurableDeliveryTransport,
	handler AssistantMentionHandler,
	consumer string,
	logger *slog.Logger,
) *AssistantMentionedConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "assistant-worker"
	}
	return &AssistantMentionedConsumer{
		transport: transport,
		handler:   handler,
		consumer:  consumer,
		logger:    logger,
	}
}

func (c *AssistantMentionedConsumer) EnsureGroup(ctx context.Context) error {
	if c == nil || c.transport == nil {
		return fmt.Errorf("assistant mentioned consumer transport not configured")
	}
	return c.transport.EnsureDurableConsumerGroup(
		ctx,
		AssistantMentionedStream,
		AssistantMentionedConsumerGroup,
		"0",
	)
}

func (c *AssistantMentionedConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.transport == nil || c.handler == nil {
		return 0, fmt.Errorf("assistant mentioned consumer not configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		return 0, err
	}
	messages, err := c.transport.ReadDurable(
		ctx,
		runtimemessaging.StreamReadRequest{
			Stream:   AssistantMentionedStream,
			Group:    AssistantMentionedConsumerGroup,
			Consumer: c.consumer,
			Count:    10,
			Block:    200 * time.Millisecond,
		},
	)
	if err != nil {
		return 0, err
	}
	processed := 0
	for _, msg := range messages {
		dedupKey := assistantMentionDedupKey(msg)
		if dedupKey != "" {
			claimed, err := c.transport.ClaimDurableDelivery(
				ctx,
				dedupKey,
				msg.ID,
				assistantMentionDedupTTL,
			)
			if err != nil {
				return processed, err
			}
			if !claimed {
				if err := c.transport.AckDurable(
					ctx,
					AssistantMentionedStream,
					AssistantMentionedConsumerGroup,
					msg.ID,
				); err != nil {
					return processed, err
				}
				processed++
				continue
			}
		}
		if err := c.processMessage(ctx, msg); err != nil {
			c.logger.Error(
				"assistant mentioned consume failed",
				"streamId",
				msg.ID,
				"errorDigest",
				assistantMentionErrorDigest(err),
			)
			if dedupKey != "" {
				_ = c.transport.ReleaseDurableDelivery(ctx, dedupKey)
			}
			if _, dlqErr := c.transport.PublishDeadLetter(
				ctx,
				runtimemessaging.DeadLetterMessage{
					SourceStream:      AssistantMentionedStream,
					DestinationStream: AssistantMentionedDeadLetter,
					SourceID:          msg.ID,
					Reason:            assistantMentionDeadLetterReason,
					Fields:            deadLetterFields(msg, err),
				},
			); dlqErr != nil {
				return processed, fmt.Errorf("assistant mentioned dlq: %w", dlqErr)
			}
			if expireErr := c.transport.SetDurableRetention(
				ctx,
				AssistantMentionedDeadLetter,
				assistantMentionDeadLetterTTL,
			); expireErr != nil {
				return processed, fmt.Errorf("retain assistant mentioned dlq: %w", expireErr)
			}
			if ackErr := c.transport.AckDurable(
				ctx,
				AssistantMentionedStream,
				AssistantMentionedConsumerGroup,
				msg.ID,
			); ackErr != nil {
				return processed, fmt.Errorf("ack dead-lettered assistant mention: %w", ackErr)
			}
			application.RecordAssistantMentionedConsumerDLQ()
			processed++
			continue
		}
		if err := c.transport.AckDurable(
			ctx,
			AssistantMentionedStream,
			AssistantMentionedConsumerGroup,
			msg.ID,
		); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}

func (c *AssistantMentionedConsumer) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 500 * time.Millisecond
	}
	if err := c.EnsureGroup(ctx); err != nil {
		c.logger.Error("assistant mentioned consumer ensure group failed", "err", err)
		return
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		if _, err := c.ProcessOnce(ctx); err != nil {
			c.logger.Error("assistant mentioned consumer tick failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *AssistantMentionedConsumer) processMessage(
	ctx context.Context,
	msg runtimemessaging.StreamDelivery,
) error {
	return c.handler.HandleAssistantMentioned(ctx, application.AssistantMentionedEvent{
		ConversationID:    durableFieldValue(msg.Fields, "conversationId"),
		MessageID:         durableFieldValue(msg.Fields, "messageId"),
		Seq:               int64Value(durableFieldValue(msg.Fields, "seq")),
		SenderID:          firstNonEmpty(durableFieldValue(msg.Fields, "senderId"), durableFieldValue(msg.Fields, "actorId")),
		Content:           durableFieldValue(msg.Fields, "content"),
		AssistantMemberID: durableFieldValue(msg.Fields, "assistantMemberId"),
		AssistantSkillID:  durableFieldValue(msg.Fields, "assistantSkillId"),
	})
}

func deadLetterFields(
	msg runtimemessaging.StreamDelivery,
	err error,
) []runtimemessaging.DurableField {
	fields := make([]runtimemessaging.DurableField, 0, len(msg.Fields)+1)
	for _, field := range msg.Fields {
		switch field.Name {
		case "error", "errorDigest", "reason", "sourceId":
			continue
		default:
			fields = append(fields, field)
		}
	}
	return append(
		fields,
		runtimemessaging.DurableField{
			Name:  "errorDigest",
			Value: assistantMentionErrorDigest(err),
		},
	)
}

func assistantMentionErrorDigest(err error) string {
	if err == nil {
		return ""
	}
	sum := sha256.Sum256([]byte(err.Error()))
	return hex.EncodeToString(sum[:])
}

func int64Value(raw string) int64 {
	value, _ := strconv.ParseInt(strings.TrimSpace(raw), 10, 64)
	return value
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func assistantMentionDedupKey(msg runtimemessaging.StreamDelivery) string {
	messageID := strings.TrimSpace(durableFieldValue(msg.Fields, "messageId"))
	if messageID == "" {
		return ""
	}
	conversationID := strings.TrimSpace(durableFieldValue(msg.Fields, "conversationId"))
	if conversationID == "" {
		return "assistant:mention:processed:" + messageID
	}
	return "assistant:mention:processed:" + conversationID + ":" + messageID
}

func durableFieldValue(fields []runtimemessaging.DurableField, name string) string {
	for _, field := range fields {
		if field.Name == name {
			return field.Value
		}
	}
	return ""
}
