package mq

import (
	"context"
	"encoding/json"
	"log/slog"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/application"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

const userProfileEventChannel = "event:user-profile"

type userDomainEvent struct {
	Type      string         `json:"type"`
	UserID    string         `json:"userId"`
	ActorID   string         `json:"actorId,omitempty"`
	Timestamp time.Time      `json:"timestamp"`
	Payload   map[string]any `json:"payload,omitempty"`
}

type UserAvatarUpdateConsumer struct {
	client        rtredis.Client
	repo          persistence.ChatRepository
	publisher     application.EventPublisher
	media         application.GroupAvatarAssetizer
	syncPublisher application.UserSyncPublisher
	scheduler     application.GroupAvatarTaskScheduler
	logger        *slog.Logger
}

func NewUserAvatarUpdateConsumer(
	client rtredis.Client,
	repo persistence.ChatRepository,
	publisher application.EventPublisher,
	media application.GroupAvatarAssetizer,
	syncPublisher application.UserSyncPublisher,
	scheduler application.GroupAvatarTaskScheduler,
	logger *slog.Logger,
) *UserAvatarUpdateConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	return &UserAvatarUpdateConsumer{
		client:        client,
		repo:          repo,
		publisher:     publisher,
		media:         media,
		syncPublisher: syncPublisher,
		scheduler:     scheduler,
		logger:        logger,
	}
}

func (c *UserAvatarUpdateConsumer) Start(ctx context.Context) error {
	if c == nil || c.client == nil || c.repo == nil {
		return nil
	}
	sub, err := c.client.Subscribe(ctx, userProfileEventChannel)
	if err != nil {
		return err
	}
	go func() {
		defer func() {
			if closeErr := sub.Close(); closeErr != nil {
				c.logger.Warn("close user avatar subscription failed", "err", closeErr)
			}
		}()
		ch := sub.Channel()
		for {
			select {
			case <-ctx.Done():
				return
			case msg, ok := <-ch:
				if !ok {
					return
				}
				c.handleMessage(ctx, msg.Payload)
			}
		}
	}()
	return nil
}

func (c *UserAvatarUpdateConsumer) handleMessage(ctx context.Context, payload string) {
	var event userDomainEvent
	if err := json.Unmarshal([]byte(payload), &event); err != nil {
		c.logger.Warn("decode user profile event failed", "err", err)
		return
	}
	if strings.TrimSpace(event.Type) != "UserAvatarUpdated" {
		return
	}
	update := application.UserAvatarUpdatedPayload{
		UserID:        stringValue(event.Payload["userId"], event.UserID),
		AvatarURL:     stringValue(event.Payload["avatarUrl"], ""),
		AvatarAssetID: stringValue(event.Payload["avatarAssetId"], ""),
		AvatarVersion: int64Value(event.Payload["avatarVersion"]),
	}
	if err := application.HandleUserAvatarUpdated(
		ctx,
		c.repo,
		c.publisher,
		c.media,
		c.syncPublisher,
		c.scheduler,
		update,
	); err != nil {
		c.logger.Error("handle user avatar updated failed", "err", err, "userId", update.UserID)
	}
}

func stringValue(value any, fallback string) string {
	if text, ok := value.(string); ok {
		text = strings.TrimSpace(text)
		if text != "" {
			return text
		}
	}
	return strings.TrimSpace(fallback)
}

func int64Value(value any) int64 {
	switch typed := value.(type) {
	case int:
		return int64(typed)
	case int32:
		return int64(typed)
	case int64:
		return typed
	case float64:
		return int64(typed)
	case json.Number:
		parsed, _ := typed.Int64()
		return parsed
	case string:
		parsed, _ := strconv.ParseInt(strings.TrimSpace(typed), 10, 64)
		return parsed
	default:
		return 0
	}
}
