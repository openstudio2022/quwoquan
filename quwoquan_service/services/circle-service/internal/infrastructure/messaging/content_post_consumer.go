package messaging

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	ContentPostPublishedChannel = "events.content.PostPublished"
	ContentPostDeletedChannel   = "events.content.PostDeleted"
	ContentPostSettingsChannel  = "events.content.PostSettingsUpdated"
)

type CirclePostCountStore interface {
	IncrementPostCount(ctx context.Context, id string, delta int64) error
}

// ContentPostConsumer 消费 content-service 帖子生命周期事件，维护圈子读模型统计。
type ContentPostConsumer struct {
	redis  rtredis.Client
	store  CirclePostCountStore
	logger *slog.Logger
}

func NewContentPostConsumer(redis rtredis.Client, store CirclePostCountStore, logger *slog.Logger) *ContentPostConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	return &ContentPostConsumer{redis: redis, store: store, logger: logger}
}

func (c *ContentPostConsumer) Run(ctx context.Context) {
	if c == nil || c.redis == nil || c.store == nil {
		return
	}
	sub, err := c.redis.Subscribe(ctx, ContentPostPublishedChannel, ContentPostDeletedChannel, ContentPostSettingsChannel)
	if err != nil {
		c.logger.Error("content post consumer subscribe failed", "err", err)
		return
	}
	defer sub.Close()

	for {
		select {
		case <-ctx.Done():
			return
		case msg, ok := <-sub.Channel():
			if !ok {
				return
			}
			if err := c.ProcessMessage(ctx, msg.Channel, msg.Payload); err != nil {
				c.logger.Warn("content post event apply failed", "channel", msg.Channel, "err", err)
			}
		}
	}
}

func (c *ContentPostConsumer) ProcessMessage(ctx context.Context, channel string, payload string) error {
	if c == nil || c.store == nil {
		return fmt.Errorf("content post consumer not configured")
	}
	evt, err := decodeContentPostEnvelope(payload)
	if err != nil {
		return err
	}
	delta := int64(0)
	switch strings.TrimSpace(evt.Type) {
	case "PostPublished":
		delta = 1
	case "PostDeleted":
		if evt.Status != "published" {
			return nil
		}
		delta = -1
	case "PostSettingsUpdated":
		if evt.Status != "published" {
			return nil
		}
		for _, circleID := range evt.AddedCircleIDs {
			if strings.TrimSpace(circleID) == "" {
				continue
			}
			if err := c.store.IncrementPostCount(ctx, strings.TrimSpace(circleID), 1); err != nil {
				return err
			}
		}
		for _, circleID := range evt.RemovedCircleIDs {
			if strings.TrimSpace(circleID) == "" {
				continue
			}
			if err := c.store.IncrementPostCount(ctx, strings.TrimSpace(circleID), -1); err != nil {
				return err
			}
		}
		return nil
	default:
		switch channel {
		case ContentPostPublishedChannel:
			delta = 1
		case ContentPostDeletedChannel:
			delta = -1
		default:
			return nil
		}
	}
	for _, circleID := range evt.CircleIDs {
		if strings.TrimSpace(circleID) == "" {
			continue
		}
		if err := c.store.IncrementPostCount(ctx, strings.TrimSpace(circleID), delta); err != nil {
			return err
		}
	}
	return nil
}

type contentPostEnvelope struct {
	Payload struct {
		Type string `json:"type"`
		Data struct {
			Status           string   `json:"status"`
			CircleIDs        []string `json:"circleIds"`
			AddedCircleIDs   []string `json:"addedCircleIds"`
			RemovedCircleIDs []string `json:"removedCircleIds"`
		} `json:"data"`
	} `json:"payload"`
}

type contentPostEvent struct {
	Type             string
	Status           string
	CircleIDs        []string
	AddedCircleIDs   []string
	RemovedCircleIDs []string
}

func decodeContentPostEnvelope(raw string) (contentPostEvent, error) {
	var envelope contentPostEnvelope
	if err := json.Unmarshal([]byte(raw), &envelope); err != nil {
		return contentPostEvent{}, err
	}
	return contentPostEvent{
		Type:             strings.TrimSpace(envelope.Payload.Type),
		Status:           strings.TrimSpace(envelope.Payload.Data.Status),
		CircleIDs:        envelope.Payload.Data.CircleIDs,
		AddedCircleIDs:   envelope.Payload.Data.AddedCircleIDs,
		RemovedCircleIDs: envelope.Payload.Data.RemovedCircleIDs,
	}, nil
}
