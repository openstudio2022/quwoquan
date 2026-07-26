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

type redisPendingClaimer interface {
	XAutoClaim(ctx context.Context, stream string, group string, consumer string, minIdle time.Duration, start string, count int64) ([]rtredis.StreamMessage, string, error)
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
	taskID := strings.TrimSpace(task.TaskID)
	if taskID == "" {
		return fmt.Errorf("reliabletask: ready task id is required")
	}
	markerKey := r.readyMarkerKey(taskID)
	claimed, err := r.client.SetNX(ctx, markerKey, taskID, 0)
	if err != nil {
		return err
	}
	if !claimed {
		return nil
	}
	_, err = r.client.XAdd(ctx, r.stream, map[string]string{
		"taskId":         taskID,
		"taskType":       strings.TrimSpace(task.TaskType),
		"outboxId":       strings.TrimSpace(task.OutboxID),
		"dedupeKey":      strings.TrimSpace(task.DedupeKey),
		"idempotencyKey": strings.TrimSpace(task.IdempotencyKey),
		"queue":          r.queue,
	})
	if err != nil {
		_ = r.client.Del(ctx, markerKey)
	}
	return err
}

func (r *RedisReadyIndex) readyMarkerKey(taskID string) string {
	return r.stream + ":queued:" + strings.TrimSpace(taskID)
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
	if err := r.client.XAck(ctx, stream, r.group, message.RawID); err != nil {
		return err
	}
	return r.client.Del(ctx, r.readyMarkerKey(message.TaskID))
}

// Purge removes one discarded execution's disposable stream and the exact
// marker keys derived from its Mongo task IDs. Streams are execution-scoped.
func (r *RedisReadyIndex) Purge(ctx context.Context, taskIDs []string) error {
	keys := make([]string, 0, len(taskIDs)+1)
	keys = append(keys, r.stream)
	seen := make(map[string]struct{}, len(taskIDs))
	for _, taskID := range taskIDs {
		taskID = strings.TrimSpace(taskID)
		if taskID == "" {
			continue
		}
		markerKey := r.readyMarkerKey(taskID)
		if _, exists := seen[markerKey]; exists {
			continue
		}
		seen[markerKey] = struct{}{}
		keys = append(keys, markerKey)
	}
	return r.client.Del(ctx, keys...)
}

func (r *RedisReadyIndex) ReclaimPending(ctx context.Context, consumer string, minIdle time.Duration, count int64) ([]ReadyIndexMessage, error) {
	if err := r.Ensure(ctx); err != nil {
		return nil, err
	}
	claimer, ok := r.client.(redisPendingClaimer)
	if !ok {
		return nil, nil
	}
	if count <= 0 {
		count = 100
	}
	messages, _, err := claimer.XAutoClaim(ctx, r.stream, r.group, consumer, minIdle, "0-0", count)
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
