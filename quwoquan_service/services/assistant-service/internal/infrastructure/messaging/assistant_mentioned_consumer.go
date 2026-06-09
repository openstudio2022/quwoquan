package messaging

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/application"
)

const (
	AssistantMentionedStream        = "events.chat.assistant_mentions"
	AssistantMentionedDeadLetter    = "events.chat.assistant_mentions.dlq"
	AssistantMentionedConsumerGroup = "assistant-service"
	assistantMentionDedupTTL        = 24 * time.Hour
)

type AssistantMentionHandler interface {
	HandleAssistantMentioned(ctx context.Context, evt application.AssistantMentionedEvent) error
}

type AssistantMentionedConsumer struct {
	redis    rtredis.Client
	handler  AssistantMentionHandler
	consumer string
	logger   *slog.Logger
}

func NewAssistantMentionedConsumer(redis rtredis.Client, handler AssistantMentionHandler, consumer string, logger *slog.Logger) *AssistantMentionedConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "assistant-worker"
	}
	return &AssistantMentionedConsumer{redis: redis, handler: handler, consumer: consumer, logger: logger}
}

func (c *AssistantMentionedConsumer) EnsureGroup(ctx context.Context) error {
	if c == nil || c.redis == nil {
		return fmt.Errorf("assistant mentioned consumer redis not configured")
	}
	return c.redis.XGroupCreateMkStream(ctx, AssistantMentionedStream, AssistantMentionedConsumerGroup, "0")
}

func (c *AssistantMentionedConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.redis == nil || c.handler == nil {
		return 0, fmt.Errorf("assistant mentioned consumer not configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		return 0, err
	}
	messages, err := c.redis.XReadGroup(
		ctx,
		AssistantMentionedConsumerGroup,
		c.consumer,
		map[string]string{AssistantMentionedStream: ">"},
		10,
		200*time.Millisecond,
	)
	if err != nil {
		return 0, err
	}
	processed := 0
	for _, msg := range messages {
		dedupKey := assistantMentionDedupKey(msg)
		if dedupKey != "" {
			claimed, err := c.redis.SetNX(ctx, dedupKey, msg.ID, assistantMentionDedupTTL)
			if err != nil {
				return processed, err
			}
			if !claimed {
				if err := c.redis.XAck(ctx, AssistantMentionedStream, AssistantMentionedConsumerGroup, msg.ID); err != nil {
					return processed, err
				}
				processed++
				continue
			}
		}
		if err := c.processMessage(ctx, msg); err != nil {
			c.logger.Error("assistant mentioned consume failed", "streamId", msg.ID, "err", err)
			if dedupKey != "" {
				_ = c.redis.Del(ctx, dedupKey)
			}
			if _, dlqErr := c.redis.XAdd(ctx, AssistantMentionedDeadLetter, deadLetterValues(msg, err)); dlqErr != nil {
				return processed, fmt.Errorf("assistant mentioned dlq: %w", dlqErr)
			}
			processed++
			continue
		}
		if err := c.redis.XAck(ctx, AssistantMentionedStream, AssistantMentionedConsumerGroup, msg.ID); err != nil {
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

func (c *AssistantMentionedConsumer) processMessage(ctx context.Context, msg rtredis.StreamMessage) error {
	return c.handler.HandleAssistantMentioned(ctx, application.AssistantMentionedEvent{
		ConversationID:    msg.Values["conversationId"],
		MessageID:         msg.Values["messageId"],
		Seq:               int64Value(msg.Values["seq"]),
		SenderID:          firstNonEmpty(msg.Values["senderId"], msg.Values["actorId"]),
		Content:           msg.Values["content"],
		AssistantMemberID: msg.Values["assistantMemberId"],
		AssistantSkillID:  msg.Values["assistantSkillId"],
	})
}

func deadLetterValues(msg rtredis.StreamMessage, err error) map[string]string {
	values := map[string]string{
		"streamId": msg.ID,
		"error":    err.Error(),
	}
	for key, value := range msg.Values {
		values[key] = value
	}
	return values
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

func assistantMentionDedupKey(msg rtredis.StreamMessage) string {
	messageID := strings.TrimSpace(msg.Values["messageId"])
	if messageID == "" {
		return ""
	}
	conversationID := strings.TrimSpace(msg.Values["conversationId"])
	if conversationID == "" {
		return "assistant:mention:processed:" + messageID
	}
	return "assistant:mention:processed:" + conversationID + ":" + messageID
}
