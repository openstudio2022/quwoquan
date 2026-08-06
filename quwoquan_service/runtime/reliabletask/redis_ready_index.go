package reliabletask

import (
	"context"
	"fmt"
	"sort"
	"strconv"
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

// ReadyIndexObservationEntry is the non-secret, read-only projection of one
// execution-scoped Redis stream entry. It intentionally omits outbox and
// idempotency values; the Mongo task is the authoritative job identity.
type ReadyIndexObservationEntry struct {
	TaskID     string
	EnqueuedAt time.Time
}

// ReadyIndexObservation is a bounded snapshot. Observe never creates a stream
// or consumer group and never claims, acknowledges, trims, or deletes data.
type ReadyIndexObservation struct {
	Entries      []ReadyIndexObservationEntry
	PendingCount int64
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

// Observe reads one already-provisioned execution stream without mutation.
// The caller must construct RedisReadyIndex from the exact executionId-derived
// stream and group. A bounded limit prevents evidence collection from becoming
// an unbounded production queue scan.
func (r *RedisReadyIndex) Observe(
	ctx context.Context,
	limit int64,
) (ReadyIndexObservation, error) {
	if limit <= 0 || limit > 1_000_000 {
		return ReadyIndexObservation{}, fmt.Errorf(
			"reliabletask: ready index observation limit must be between 1 and 1000000",
		)
	}
	messages, err := r.client.XRead(
		ctx,
		map[string]string{r.stream: "0-0"},
		limit+1,
		0,
	)
	if err != nil {
		return ReadyIndexObservation{}, fmt.Errorf(
			"reliabletask: read ready index observation: %w",
			err,
		)
	}
	if int64(len(messages)) > limit {
		return ReadyIndexObservation{}, fmt.Errorf(
			"reliabletask: ready index observation exceeds bounded limit %d",
			limit,
		)
	}
	entries := make([]ReadyIndexObservationEntry, 0, len(messages))
	for _, message := range messages {
		if strings.TrimSpace(message.Stream) != r.stream {
			return ReadyIndexObservation{}, fmt.Errorf(
				"reliabletask: ready index observation crossed execution stream",
			)
		}
		taskID := strings.TrimSpace(message.Values["taskId"])
		if taskID == "" {
			return ReadyIndexObservation{}, fmt.Errorf(
				"reliabletask: ready index observation contains empty taskId",
			)
		}
		milliseconds, _, ok := strings.Cut(strings.TrimSpace(message.ID), "-")
		if !ok {
			return ReadyIndexObservation{}, fmt.Errorf(
				"reliabletask: ready index observation contains invalid stream id",
			)
		}
		epoch, parseErr := strconv.ParseInt(milliseconds, 10, 64)
		if parseErr != nil || epoch < 1 {
			return ReadyIndexObservation{}, fmt.Errorf(
				"reliabletask: ready index observation contains invalid stream time",
			)
		}
		entries = append(entries, ReadyIndexObservationEntry{
			TaskID:     taskID,
			EnqueuedAt: time.UnixMilli(epoch).UTC(),
		})
	}
	sort.Slice(entries, func(i, j int) bool {
		if entries[i].EnqueuedAt.Equal(entries[j].EnqueuedAt) {
			return entries[i].TaskID < entries[j].TaskID
		}
		return entries[i].EnqueuedAt.Before(entries[j].EnqueuedAt)
	})
	pending, err := r.client.XPendingCount(ctx, r.stream, r.group)
	if err != nil {
		return ReadyIndexObservation{}, fmt.Errorf(
			"reliabletask: read ready index pending count: %w",
			err,
		)
	}
	return ReadyIndexObservation{Entries: entries, PendingCount: pending}, nil
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
