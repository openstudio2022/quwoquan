package reliabletask

import (
	"context"
	"fmt"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

type RedisReadyIndex struct {
	client rtredis.Client
	stream string
	group  string
	queue  string
}

type RedisReadyIndexConfig struct {
	Client rtredis.Client
	Stream string
	Group  string
	Queue  string
}

func NewRedisReadyIndex(cfg RedisReadyIndexConfig) (*RedisReadyIndex, error) {
	if cfg.Client == nil {
		return nil, fmt.Errorf("reliabletask: redis ready index client is required")
	}
	stream := strings.TrimSpace(cfg.Stream)
	if stream == "" {
		stream = "reliabletask:ready:chat:avatar"
	}
	group := strings.TrimSpace(cfg.Group)
	if group == "" {
		group = "chat.group_avatar_worker"
	}
	return &RedisReadyIndex{
		client: cfg.Client,
		stream: stream,
		group:  group,
		queue:  strings.TrimSpace(cfg.Queue),
	}, nil
}

func (r *RedisReadyIndex) Ensure(ctx context.Context) error {
	return r.client.XGroupCreateMkStream(ctx, r.stream, r.group, "0")
}

func (r *RedisReadyIndex) EnqueueReadyOrMerge(ctx context.Context, task ReliableAsyncTask) error {
	if err := r.Ensure(ctx); err != nil {
		return err
	}
	_, err := r.client.XAdd(ctx, r.stream, map[string]string{
		"taskId":         strings.TrimSpace(task.TaskID),
		"taskType":       strings.TrimSpace(task.TaskType),
		"outboxId":       strings.TrimSpace(task.OutboxID),
		"dedupeKey":      strings.TrimSpace(task.DedupeKey),
		"idempotencyKey": strings.TrimSpace(task.IdempotencyKey),
		"queue":          r.queue,
	})
	return err
}

func (r *RedisReadyIndex) Claim(ctx context.Context, consumer string, count int64, block time.Duration) ([]ReadyIndexMessage, error) {
	if err := r.Ensure(ctx); err != nil {
		return nil, err
	}
	messages, err := r.client.XReadGroup(ctx, r.group, consumer, map[string]string{r.stream: ">"}, count, block)
	if err != nil {
		return nil, err
	}
	out := make([]ReadyIndexMessage, 0, len(messages))
	for _, message := range messages {
		taskID := strings.TrimSpace(message.Values["taskId"])
		if taskID == "" {
			_ = r.client.XAck(ctx, message.Stream, r.group, message.ID)
			continue
		}
		out = append(out, ReadyIndexMessage{
			StreamID: message.Stream,
			TaskID:   taskID,
			TaskType: strings.TrimSpace(message.Values["taskType"]),
			Queue:    strings.TrimSpace(message.Values["queue"]),
			RawID:    message.ID,
		})
	}
	return out, nil
}

func (r *RedisReadyIndex) Ack(ctx context.Context, message ReadyIndexMessage) error {
	stream := strings.TrimSpace(message.StreamID)
	if stream == "" {
		stream = r.stream
	}
	return r.client.XAck(ctx, stream, r.group, message.RawID)
}
