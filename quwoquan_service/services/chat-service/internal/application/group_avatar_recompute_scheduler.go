package application

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sort"
	"strings"
	"sync"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

const (
	groupAvatarTaskKindRecompute = "recompute"
	groupAvatarTaskKindPatch     = "conversation_avatar_patch"

	groupAvatarTaskStatusQueued          = "queued"
	groupAvatarTaskStatusProcessing      = "processing"
	groupAvatarTaskStatusTransientFailed = "transient_failed"
	groupAvatarTaskStatusTerminalFailed  = "terminal_failed"
)

const (
	groupAvatarTaskIndexKey = "chat:group-avatar:task:index"
	groupAvatarTaskQueueKey = "chat:group-avatar:task:queue"
	groupAvatarTaskLockTTL  = 15 * time.Second
)

type GroupAvatarRecomputeTask struct {
	ConversationID string
	ActorID        string
	Trigger        string
}

type ConversationAvatarPatchTask struct {
	ConversationID   string
	ActorID          string
	Trigger          string
	Payload          map[string]any
	RecipientUserIDs []string
}

type groupAvatarTaskRecord struct {
	ID               string         `json:"id"`
	Kind             string         `json:"kind"`
	ConversationID   string         `json:"conversationId"`
	ActorID          string         `json:"actorId"`
	Trigger          string         `json:"trigger"`
	Payload          map[string]any `json:"payload,omitempty"`
	RecipientUserIDs []string       `json:"recipientUserIds,omitempty"`
	Status           string         `json:"status"`
	Revision         int64          `json:"revision"`
	Attempts         int            `json:"attempts"`
	NextAttemptAt    time.Time      `json:"nextAttemptAt"`
	UpdatedAt        time.Time      `json:"updatedAt"`
	LastError        string         `json:"lastError,omitempty"`
}

type RedisGroupAvatarTaskScheduler struct {
	client          rtredis.Client
	repo            persistence.ChatRepository
	publisher       EventPublisher
	media           GroupAvatarAssetizer
	syncPublisher   UserSyncPublisher
	logger          *slog.Logger
	pollInterval    time.Duration
	maxAttempts     int
	drainBatchSize  int
	fanoutBatchSize int
	metrics         *groupAvatarSchedulerMetrics
	startOnce       sync.Once
}

func NewRedisGroupAvatarTaskScheduler(
	client rtredis.Client,
	repo persistence.ChatRepository,
	publisher EventPublisher,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	logger *slog.Logger,
) *RedisGroupAvatarTaskScheduler {
	if logger == nil {
		logger = slog.Default()
	}
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	return &RedisGroupAvatarTaskScheduler{
		client:          client,
		repo:            repo,
		publisher:       publisher,
		media:           media,
		syncPublisher:   syncPublisher,
		logger:          logger,
		pollInterval:    50 * time.Millisecond,
		maxAttempts:     5,
		drainBatchSize:  32,
		fanoutBatchSize: 100,
		metrics:         newGroupAvatarSchedulerMetrics(),
	}
}

func (s *RedisGroupAvatarTaskScheduler) Start(ctx context.Context) error {
	if s == nil || s.client == nil || s.repo == nil {
		return nil
	}
	s.startOnce.Do(func() {
		go func() {
			ticker := time.NewTicker(s.pollInterval)
			defer ticker.Stop()
			for {
				s.drainOnce(ctx)
				select {
				case <-ctx.Done():
					return
				case <-ticker.C:
				}
			}
		}()
	})
	return nil
}

func (s *RedisGroupAvatarTaskScheduler) EnqueueRecompute(ctx context.Context, task GroupAvatarRecomputeTask) error {
	record := groupAvatarTaskRecord{
		ID:             recomputeTaskID(task.ConversationID),
		Kind:           groupAvatarTaskKindRecompute,
		ConversationID: strings.TrimSpace(task.ConversationID),
		ActorID:        strings.TrimSpace(task.ActorID),
		Trigger:        strings.TrimSpace(task.Trigger),
	}
	return s.enqueue(ctx, record, false)
}

func (s *RedisGroupAvatarTaskScheduler) EnqueueConversationAvatarPatch(ctx context.Context, task ConversationAvatarPatchTask) error {
	record := groupAvatarTaskRecord{
		ID:               patchTaskID(task.ConversationID, task.Payload),
		Kind:             groupAvatarTaskKindPatch,
		ConversationID:   strings.TrimSpace(task.ConversationID),
		ActorID:          strings.TrimSpace(task.ActorID),
		Trigger:          strings.TrimSpace(task.Trigger),
		Payload:          cloneMap(task.Payload),
		RecipientUserIDs: dedupeSortedUserIDs(task.RecipientUserIDs),
	}
	return s.enqueue(ctx, record, false)
}

func (s *RedisGroupAvatarTaskScheduler) enqueue(
	ctx context.Context,
	record groupAvatarTaskRecord,
	mergeRecipients bool,
) error {
	if s == nil || s.client == nil {
		return nil
	}
	if strings.TrimSpace(record.ConversationID) == "" || strings.TrimSpace(record.ID) == "" {
		return nil
	}
	now := time.Now().UTC()
	record.Status = groupAvatarTaskStatusQueued
	record.NextAttemptAt = now
	record.UpdatedAt = now

	existing, ok, err := s.loadTask(ctx, record.ID)
	if err != nil {
		return err
	}
	if ok {
		record.Revision = existing.Revision + 1
		if mergeRecipients {
			record.RecipientUserIDs = unionUserIDs(existing.RecipientUserIDs, record.RecipientUserIDs)
		}
	} else {
		record.Revision = 1
	}
	record.Attempts = 0
	record.LastError = ""
	return s.saveTask(ctx, record)
}

func (s *RedisGroupAvatarTaskScheduler) drainOnce(ctx context.Context) {
	if s == nil || s.client == nil {
		return
	}
	taskIDs, err := s.client.ZRangeByScore(
		ctx,
		groupAvatarTaskQueueKey,
		0,
		float64(time.Now().UTC().UnixMilli()),
		s.drainBatchSize,
	)
	if err != nil {
		s.logger.Error("list due group avatar tasks failed", "err", err)
		return
	}
	for _, taskID := range taskIDs {
		task, ok, err := s.loadTask(ctx, taskID)
		if err != nil || !ok {
			continue
		}
		now := time.Now().UTC()
		if task.Status == groupAvatarTaskStatusTerminalFailed || task.NextAttemptAt.After(now) {
			continue
		}
		lockKey := s.lockKey(task.ID)
		acquired, err := s.client.SetNX(ctx, lockKey, task.ID, groupAvatarTaskLockTTL)
		if err != nil || !acquired {
			continue
		}
		func() {
			defer func() {
				_ = s.client.Del(ctx, lockKey)
			}()
			s.handleTask(ctx, task)
		}()
	}
}

func (s *RedisGroupAvatarTaskScheduler) handleTask(ctx context.Context, task groupAvatarTaskRecord) {
	current, ok, err := s.loadTask(ctx, task.ID)
	if err != nil || !ok {
		return
	}
	now := time.Now().UTC()
	if current.Status == groupAvatarTaskStatusTerminalFailed || current.NextAttemptAt.After(now) {
		return
	}
	current.Status = groupAvatarTaskStatusProcessing
	current.NextAttemptAt = now.Add(groupAvatarTaskLockTTL)
	current.UpdatedAt = now
	if err := s.saveTask(ctx, current); err != nil {
		s.logger.Error("mark group avatar task processing failed", "err", err, "taskId", task.ID)
		return
	}

	var runErr error
	start := time.Now()
	switch current.Kind {
	case groupAvatarTaskKindRecompute:
		runErr = RecomputeGroupAvatar(
			context.Background(),
			s.repo,
			s.publisher,
			s.media,
			s.syncPublisher,
			s,
			current.ConversationID,
			current.ActorID,
		)
	case groupAvatarTaskKindPatch:
		runErr = s.runPatchTask(context.Background(), current)
	default:
		runErr = fmt.Errorf("unknown group avatar task kind: %s", current.Kind)
	}
	s.metrics.recordTask(current.Kind, time.Since(start))

	latest, ok, err := s.loadTask(ctx, current.ID)
	if err != nil || !ok {
		return
	}
	if latest.Revision > current.Revision {
		latest.Status = groupAvatarTaskStatusQueued
		latest.Attempts = 0
		latest.NextAttemptAt = time.Now().UTC()
		latest.UpdatedAt = time.Now().UTC()
		latest.LastError = ""
		if err := s.saveTask(ctx, latest); err != nil {
			s.logger.Error("reschedule superseded group avatar task failed", "err", err, "taskId", current.ID)
		}
		return
	}
	if runErr == nil {
		if err := s.deleteTask(ctx, current.ID); err != nil {
			s.logger.Error("delete completed group avatar task failed", "err", err, "taskId", current.ID)
		}
		return
	}

	latest.Attempts = current.Attempts + 1
	latest.UpdatedAt = time.Now().UTC()
	latest.LastError = runErr.Error()
	if latest.Attempts >= s.maxAttempts {
		latest.Status = groupAvatarTaskStatusTerminalFailed
		latest.NextAttemptAt = latest.UpdatedAt
		s.metrics.recordTerminalFailure()
	} else {
		latest.Status = groupAvatarTaskStatusTransientFailed
		latest.NextAttemptAt = latest.UpdatedAt.Add(retryBackoff(latest.Attempts))
		s.metrics.recordTransientFailure()
	}
	if err := s.saveTask(ctx, latest); err != nil {
		s.logger.Error("persist failed group avatar task failed", "err", err, "taskId", current.ID)
		return
	}
	s.logger.Error(
		"group avatar task failed",
		"err",
		runErr,
		"taskId",
		current.ID,
		"kind",
		current.Kind,
		"conversationId",
		current.ConversationID,
		"attempts",
		latest.Attempts,
		"status",
		latest.Status,
	)
}

func (s *RedisGroupAvatarTaskScheduler) runPatchTask(ctx context.Context, task groupAvatarTaskRecord) error {
	if s.syncPublisher == nil {
		return nil
	}
	failedRecipients := make([]string, 0)
	for start := 0; start < len(task.RecipientUserIDs); start += s.fanoutBatchSize {
		end := start + s.fanoutBatchSize
		if end > len(task.RecipientUserIDs) {
			end = len(task.RecipientUserIDs)
		}
		batch := task.RecipientUserIDs[start:end]
		s.metrics.recordPatchBatch(len(batch))
		result, err := s.syncPublisher.AppendPatchBatch(
			ctx,
			batch,
			"conversation.avatar.updated",
			task.Payload,
		)
		if err != nil {
			failedRecipients = append(failedRecipients, batch...)
			continue
		}
		if len(result.FailedUserIDs) > 0 {
			failedRecipients = append(failedRecipients, result.FailedUserIDs...)
		}
	}
	if len(failedRecipients) == 0 {
		return nil
	}
	task.RecipientUserIDs = failedRecipients
	task.Status = groupAvatarTaskStatusQueued
	task.NextAttemptAt = time.Now().UTC()
	task.UpdatedAt = time.Now().UTC()
	if err := s.saveTask(ctx, task); err != nil {
		return err
	}
	return fmt.Errorf("conversation avatar patch fanout partial failure: %d recipients pending retry", len(failedRecipients))
}

func (s *RedisGroupAvatarTaskScheduler) loadTask(ctx context.Context, taskID string) (groupAvatarTaskRecord, bool, error) {
	value, err := s.client.HGet(ctx, groupAvatarTaskIndexKey, strings.TrimSpace(taskID))
	if err != nil {
		if err == rtredis.ErrKeyNotFound {
			return groupAvatarTaskRecord{}, false, nil
		}
		return groupAvatarTaskRecord{}, false, err
	}
	task, err := decodeGroupAvatarTask(value)
	if err != nil {
		return groupAvatarTaskRecord{}, false, err
	}
	return task, true, nil
}

func (s *RedisGroupAvatarTaskScheduler) saveTask(ctx context.Context, task groupAvatarTaskRecord) error {
	body, err := json.Marshal(task)
	if err != nil {
		return err
	}
	if err := s.client.HSet(ctx, groupAvatarTaskIndexKey, task.ID, string(body)); err != nil {
		return err
	}
	if task.Status == groupAvatarTaskStatusTerminalFailed {
		return s.client.ZRem(ctx, groupAvatarTaskQueueKey, task.ID)
	}
	return s.client.ZAdd(
		ctx,
		groupAvatarTaskQueueKey,
		float64(task.NextAttemptAt.UTC().UnixMilli()),
		task.ID,
	)
}

func (s *RedisGroupAvatarTaskScheduler) deleteTask(ctx context.Context, taskID string) error {
	taskID = strings.TrimSpace(taskID)
	if err := s.client.HDel(ctx, groupAvatarTaskIndexKey, taskID); err != nil {
		return err
	}
	return s.client.ZRem(ctx, groupAvatarTaskQueueKey, taskID)
}

func (s *RedisGroupAvatarTaskScheduler) lockKey(taskID string) string {
	return "chat:group-avatar:task:lock:" + strings.TrimSpace(taskID)
}

func decodeGroupAvatarTask(encoded string) (groupAvatarTaskRecord, error) {
	var task groupAvatarTaskRecord
	if err := json.Unmarshal([]byte(encoded), &task); err != nil {
		return groupAvatarTaskRecord{}, err
	}
	return task, nil
}

func retryBackoff(attempt int) time.Duration {
	if attempt <= 1 {
		return 200 * time.Millisecond
	}
	if attempt == 2 {
		return 500 * time.Millisecond
	}
	if attempt == 3 {
		return 1 * time.Second
	}
	return 2 * time.Second
}

func recomputeTaskID(conversationID string) string {
	return "recompute:" + strings.TrimSpace(conversationID)
}

func patchTaskID(conversationID string, payload map[string]any) string {
	version := ""
	if value, ok := payload["groupAvatarVersion"]; ok {
		version = fmt.Sprintf("%v", value)
	}
	return fmt.Sprintf("patch:%s:%s", strings.TrimSpace(conversationID), strings.TrimSpace(version))
}

func dedupeSortedUserIDs(userIDs []string) []string {
	if len(userIDs) == 0 {
		return []string{}
	}
	seen := make(map[string]struct{}, len(userIDs))
	out := make([]string, 0, len(userIDs))
	for _, userID := range userIDs {
		normalized := strings.TrimSpace(userID)
		if normalized == "" {
			continue
		}
		if _, ok := seen[normalized]; ok {
			continue
		}
		seen[normalized] = struct{}{}
		out = append(out, normalized)
	}
	sort.Strings(out)
	return out
}

func unionUserIDs(existing []string, incoming []string) []string {
	return dedupeSortedUserIDs(append(append([]string{}, existing...), incoming...))
}

func cloneMap(input map[string]any) map[string]any {
	if len(input) == 0 {
		return map[string]any{}
	}
	out := make(map[string]any, len(input))
	for key, value := range input {
		out[key] = value
	}
	return out
}

func (s *RedisGroupAvatarTaskScheduler) MetricsSnapshot() map[string]float64 {
	if s == nil || s.client == nil {
		return map[string]float64{}
	}
	queueDepth, err := s.client.ZCard(context.Background(), groupAvatarTaskQueueKey)
	if err != nil {
		queueDepth = 0
	}
	return s.metrics.snapshot(queueDepth)
}
