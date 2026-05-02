package application

import (
	"context"
	"fmt"
	"log/slog"
	"sort"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/runtime/reliabletask"
	event "quwoquan_service/services/chat-service/internal/domain/conversation/event"
	"quwoquan_service/services/chat-service/internal/infrastructure/persistence"
)

const (
	chatGroupAvatarRecomputeTaskType = "chat.group_avatar.recompute"
	conversationAvatarUpdatedEvent   = "conversation.avatar.updated"
)

type ReliableGroupAvatarSchedulerOption func(*ReliableGroupAvatarTaskScheduler)

type ReliableGroupAvatarTaskScheduler struct {
	store         reliabletask.Store
	catalog       reliabletask.Catalog
	repo          persistence.ChatRepository
	publisher     EventPublisher
	media         GroupAvatarAssetizer
	syncPublisher UserSyncPublisher
	logger        *slog.Logger

	recomputeDelay time.Duration
	maxDelay       time.Duration
	leaseTTL       time.Duration
	tick           time.Duration
	retryPolicy    reliabletask.RetryPolicy
	env            string
	instanceID     string
	enabledModules map[string]bool
	dispatcher     *ReliableTaskOutboxDispatcher
	avatarWorker   *ReliableGroupAvatarWorker
	fanoutWorker   *ReliableAvatarNotificationFanoutWorker
	readyIndex     reliabletask.ReadyIndex
}

type ReliableTaskOutboxDispatcher struct {
	store      reliabletask.Store
	readyIndex reliabletask.ReadyIndex
	env        string
	domain     string
	module     string
	owner      string
	shardID    int
	leaseTTL   time.Duration
}

type ReliableGroupAvatarWorker struct {
	scheduler *ReliableGroupAvatarTaskScheduler
}

type ReliableAvatarNotificationFanoutWorker struct {
	scheduler *ReliableGroupAvatarTaskScheduler
}

func NewReliableGroupAvatarTaskScheduler(
	store reliabletask.Store,
	catalog reliabletask.Catalog,
	repo persistence.ChatRepository,
	publisher EventPublisher,
	media GroupAvatarAssetizer,
	syncPublisher UserSyncPublisher,
	logger *slog.Logger,
	opts ...ReliableGroupAvatarSchedulerOption,
) *ReliableGroupAvatarTaskScheduler {
	if logger == nil {
		logger = slog.Default()
	}
	if publisher == nil {
		publisher = NoopEventPublisher()
	}
	taskSpec := catalog.Tasks[chatGroupAvatarRecomputeTaskType]
	retryPolicy := taskSpec.RetryPolicyConfig()
	scheduler := &ReliableGroupAvatarTaskScheduler{
		store:          store,
		catalog:        catalog,
		repo:           repo,
		publisher:      publisher,
		media:          media,
		syncPublisher:  syncPublisher,
		logger:         logger,
		recomputeDelay: taskSpec.MergePolicy.DelayFromNow,
		maxDelay:       taskSpec.MergePolicy.MaxDelay,
		leaseTTL:       30 * time.Second,
		tick:           100 * time.Millisecond,
		retryPolicy:    retryPolicy,
		env:            "alpha",
		instanceID:     "chat-service",
		enabledModules: map[string]bool{
			"chat.task_outbox_dispatcher":         true,
			"chat.group_avatar_worker":            true,
			"chat.notification_outbox_dispatcher": true,
			"notification.fanout_worker":          true,
		},
	}
	if scheduler.recomputeDelay == 0 {
		scheduler.recomputeDelay = time.Minute
	}
	if scheduler.maxDelay == 0 {
		scheduler.maxDelay = 10 * time.Minute
	}
	for _, opt := range opts {
		if opt != nil {
			opt(scheduler)
		}
	}
	scheduler.dispatcher = &ReliableTaskOutboxDispatcher{
		store:      store,
		readyIndex: scheduler.readyIndex,
		env:        scheduler.env,
		domain:     "chat",
		module:     "chat.task_outbox_dispatcher",
		owner:      scheduler.instanceID,
		shardID:    0,
		leaseTTL:   scheduler.leaseTTL,
	}
	scheduler.avatarWorker = &ReliableGroupAvatarWorker{scheduler: scheduler}
	scheduler.fanoutWorker = &ReliableAvatarNotificationFanoutWorker{scheduler: scheduler}
	return scheduler
}

func WithReliableGroupAvatarDelay(delay time.Duration) ReliableGroupAvatarSchedulerOption {
	return func(s *ReliableGroupAvatarTaskScheduler) {
		if s != nil && delay >= 0 {
			s.recomputeDelay = delay
		}
	}
}

func WithReliableGroupAvatarTick(tick time.Duration) ReliableGroupAvatarSchedulerOption {
	return func(s *ReliableGroupAvatarTaskScheduler) {
		if s != nil && tick > 0 {
			s.tick = tick
		}
	}
}

func WithReliableGroupAvatarLeaseTTL(ttl time.Duration) ReliableGroupAvatarSchedulerOption {
	return func(s *ReliableGroupAvatarTaskScheduler) {
		if s != nil && ttl > 0 {
			s.leaseTTL = ttl
		}
	}
}

func WithReliableGroupAvatarReadyIndex(index reliabletask.ReadyIndex) ReliableGroupAvatarSchedulerOption {
	return func(s *ReliableGroupAvatarTaskScheduler) {
		if s != nil {
			s.readyIndex = index
		}
	}
}

func WithReliableGroupAvatarRuntimeIdentity(env string, instanceID string) ReliableGroupAvatarSchedulerOption {
	return func(s *ReliableGroupAvatarTaskScheduler) {
		if s == nil {
			return
		}
		if strings.TrimSpace(env) != "" {
			s.env = strings.TrimSpace(env)
		}
		if strings.TrimSpace(instanceID) != "" {
			s.instanceID = strings.TrimSpace(instanceID)
		}
	}
}

func WithReliableGroupAvatarEnabledModules(modules []string) ReliableGroupAvatarSchedulerOption {
	return func(s *ReliableGroupAvatarTaskScheduler) {
		if s == nil || len(modules) == 0 {
			return
		}
		enabled := map[string]bool{}
		for _, module := range modules {
			trimmed := strings.TrimSpace(module)
			if trimmed != "" {
				enabled[trimmed] = true
			}
		}
		s.enabledModules = enabled
	}
}

func (s *ReliableGroupAvatarTaskScheduler) Start(ctx context.Context) error {
	if s == nil || s.store == nil {
		return reliabletask.ErrStoreRequired
	}
	go s.loop(ctx)
	return nil
}

func (s *ReliableGroupAvatarTaskScheduler) loop(ctx context.Context) {
	ticker := time.NewTicker(s.tick)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := s.DrainOnce(ctx); err != nil {
				s.logger.Error("reliable group avatar scheduler drain failed", "err", err)
			}
		}
	}
}

func (s *ReliableGroupAvatarTaskScheduler) DrainOnce(ctx context.Context) error {
	if s.moduleEnabled("chat.task_outbox_dispatcher") {
		if err := s.dispatcher.DispatchDue(ctx, 100); err != nil {
			return err
		}
	}
	if s.moduleEnabled("chat.group_avatar_worker") {
		if err := s.avatarWorker.DrainOnce(ctx); err != nil {
			return err
		}
	}
	if s.moduleEnabled("chat.notification_outbox_dispatcher") || s.moduleEnabled("notification.fanout_worker") {
		if err := s.fanoutWorker.DrainOnce(ctx); err != nil {
			return err
		}
	}
	return nil
}

func (s *ReliableGroupAvatarTaskScheduler) moduleEnabled(module string) bool {
	if len(s.enabledModules) == 0 {
		return true
	}
	return s.enabledModules[module]
}

func (d *ReliableTaskOutboxDispatcher) DispatchDue(ctx context.Context, limit int) error {
	now := time.Now().UTC()
	lease, err := d.store.ClaimShardLease(ctx, reliabletask.ClaimShardLeaseRequest{
		Env:      d.env,
		Domain:   d.domain,
		Module:   d.module,
		Owner:    d.owner,
		ShardID:  d.shardID,
		LeaseTTL: d.leaseTTL,
		Now:      now,
	})
	if err != nil {
		return fmt.Errorf("claim dispatcher shard lease: %w", err)
	}
	if lease == nil {
		return nil
	}
	tasks, err := d.store.DispatchDueTasks(ctx, now, limit)
	if err != nil {
		return fmt.Errorf("dispatch due reliable task: %w", err)
	}
	if d.readyIndex != nil {
		for _, task := range tasks {
			if err := d.readyIndex.EnqueueReadyOrMerge(ctx, task); err != nil {
				return fmt.Errorf("enqueue redis ready index: %w", err)
			}
		}
	}
	return nil
}

func (w *ReliableGroupAvatarWorker) DrainOnce(ctx context.Context) error {
	s := w.scheduler
	if s.readyIndex != nil {
		return w.drainRedisReadyIndex(ctx)
	}
	now := time.Now().UTC()
	for {
		task, err := s.store.ClaimReadyTask(ctx, []string{chatGroupAvatarRecomputeTaskType}, "chat.group_avatar_worker", s.leaseTTL, now)
		if err != nil {
			return fmt.Errorf("claim group avatar task: %w", err)
		}
		if task == nil {
			break
		}
		if err := s.handleRecomputeTask(ctx, *task); err != nil {
			s.logger.Error("handle group avatar reliable task failed", "err", err, "taskId", task.TaskID)
		}
	}
	return nil
}

func (w *ReliableGroupAvatarWorker) drainRedisReadyIndex(ctx context.Context) error {
	s := w.scheduler
	for {
		messages, err := s.readyIndex.Claim(ctx, "chat.group_avatar_worker:"+s.instanceID, 20, 0)
		if err != nil {
			return fmt.Errorf("claim redis ready index: %w", err)
		}
		if len(messages) == 0 {
			break
		}
		for _, message := range messages {
			task, err := s.store.ClaimReadyTaskByID(ctx, message.TaskID, "chat.group_avatar_worker", s.leaseTTL, time.Now().UTC())
			if err != nil {
				return fmt.Errorf("claim ready task by id: %w", err)
			}
			if task == nil {
				if err := s.readyIndex.Ack(ctx, message); err != nil {
					return fmt.Errorf("ack stale redis ready index: %w", err)
				}
				continue
			}
			if err := s.handleRecomputeTask(ctx, *task); err != nil {
				s.logger.Error("handle group avatar reliable task failed", "err", err, "taskId", task.TaskID)
				continue
			}
			if err := s.readyIndex.Ack(ctx, message); err != nil {
				return fmt.Errorf("ack redis ready index: %w", err)
			}
		}
	}
	return w.drainMongoReadyQueue(ctx)
}

func (w *ReliableGroupAvatarWorker) drainMongoReadyQueue(ctx context.Context) error {
	s := w.scheduler
	now := time.Now().UTC()
	for {
		task, err := s.store.ClaimReadyTask(ctx, []string{chatGroupAvatarRecomputeTaskType}, "chat.group_avatar_worker", s.leaseTTL, now)
		if err != nil {
			return fmt.Errorf("claim group avatar task: %w", err)
		}
		if task == nil {
			break
		}
		if err := s.handleRecomputeTask(ctx, *task); err != nil {
			s.logger.Error("handle group avatar reliable task failed", "err", err, "taskId", task.TaskID)
		}
	}
	return nil
}

func (w *ReliableAvatarNotificationFanoutWorker) DrainOnce(ctx context.Context) error {
	s := w.scheduler
	for {
		notification, err := s.store.ClaimNotification(ctx, []string{conversationAvatarUpdatedEvent}, "notification.fanout_worker", s.leaseTTL, time.Now().UTC())
		if err != nil {
			return fmt.Errorf("claim avatar notification: %w", err)
		}
		if notification == nil {
			break
		}
		if err := s.handleNotification(ctx, *notification); err != nil {
			s.logger.Error("handle avatar notification failed", "err", err, "notificationId", notification.NotificationID)
		}
	}
	return nil
}

func (s *ReliableGroupAvatarTaskScheduler) EnqueueRecompute(ctx context.Context, task GroupAvatarRecomputeTask) error {
	if s == nil || s.store == nil {
		return reliabletask.ErrStoreRequired
	}
	now := time.Now().UTC()
	payload := map[string]string{
		"triggers": strings.TrimSpace(task.Trigger),
	}
	if conv, err := s.repo.FindConversationByID(ctx, task.ConversationID); err == nil {
		payload["rosterRevision"] = strconv.FormatInt(conv.MembersRosterRevision, 10)
	}
	req := reliabletask.DeclareTaskRequest{
		TaskType:        chatGroupAvatarRecomputeTaskType,
		OwnerDomain:     "chat",
		AggregateType:   "conversationId",
		AggregateID:     strings.TrimSpace(task.ConversationID),
		DedupeKey:       chatGroupAvatarRecomputeTaskType + ":" + strings.TrimSpace(task.ConversationID),
		IdempotencyKey:  chatGroupAvatarRecomputeTaskType + ":" + strings.TrimSpace(task.ConversationID),
		PartitionKey:    strings.TrimSpace(task.ConversationID),
		Payload:         payload,
		PayloadAllow:    []string{"rosterRevision", "triggers"},
		Trigger:         strings.TrimSpace(task.Trigger),
		StartAt:         now.Add(s.recomputeDelay),
		MaxDelayUntil:   now.Add(s.maxDelay),
		MergeWindow:     s.maxDelay,
		CreatedByModule: "chat.task_outbox_dispatcher",
	}
	_, err := s.store.DeclareTask(ctx, req)
	return err
}

func (s *ReliableGroupAvatarTaskScheduler) EnqueueConversationAvatarPatch(ctx context.Context, task ConversationAvatarPatchTask) error {
	if s == nil || s.store == nil {
		return reliabletask.ErrStoreRequired
	}
	record := reliabletask.NotificationOutboxRecord{
		EventType:     conversationAvatarUpdatedEvent,
		OwnerDomain:   "chat",
		AggregateType: "conversation",
		AggregateID:   strings.TrimSpace(task.ConversationID),
		DedupeKey:     conversationAvatarUpdatedEvent + ":" + strings.TrimSpace(task.ConversationID) + ":" + fmt.Sprint(task.Payload["groupAvatarVersion"]),
		Payload:       stringifyPayload(task.Payload),
		RecipientIDs:  dedupeSortedUserIDs(task.RecipientUserIDs),
		Status:        reliabletask.NotificationStatusPending,
		NextAttemptAt: time.Now().UTC(),
	}
	_, err := s.store.CreateNotification(ctx, record)
	return err
}

func (s *ReliableGroupAvatarTaskScheduler) handleRecomputeTask(ctx context.Context, task reliabletask.ReliableAsyncTask) error {
	err := RecomputeGroupAvatar(
		ctx,
		s.repo,
		s.publisher,
		s.media,
		s.syncPublisher,
		s,
		task.AggregateID,
		"",
	)
	if err != nil {
		return s.store.FailTask(ctx, task.TaskID, task.LeaseToken, reliabletask.RuntimeFailure{
			Code:    "CHAT.GROUP_AVATAR.recompute_failed",
			Message: err.Error(),
			Attributes: map[string]string{
				"conversationId": task.AggregateID,
			},
		}, s.retryPolicy, time.Now().UTC())
	}
	if err := s.store.CompleteTask(ctx, task.TaskID, task.LeaseToken); err != nil {
		return fmt.Errorf("ack group avatar task: %w", err)
	}
	return nil
}

func (s *ReliableGroupAvatarTaskScheduler) handleNotification(ctx context.Context, notification reliabletask.NotificationOutboxRecord) error {
	if s.syncPublisher == nil {
		return s.store.CompleteNotification(ctx, notification.NotificationID, notification.LeaseToken)
	}
	if err := s.store.EnsureRecipientLedgers(ctx, notification.NotificationID, notification.EventType, notification.RecipientIDs); err != nil {
		return s.retryNotification(ctx, notification, err)
	}
	pending, err := s.store.ListPendingRecipients(ctx, notification.NotificationID)
	if err != nil {
		return s.retryNotification(ctx, notification, err)
	}
	failed := false
	payload := anyPayload(notification.Payload)
	for _, ledger := range pending {
		patch, err := s.syncPublisher.AppendPatch(ctx, ledger.RecipientID, notification.EventType, payload)
		if err != nil {
			failed = true
			_ = s.store.MarkRecipientFailed(ctx, notification.NotificationID, ledger.RecipientID, reliabletask.RuntimeFailure{
				Code:    "CHAT.GROUP_AVATAR.patch_fanout_failed",
				Message: err.Error(),
			})
			continue
		}
		if err := s.store.MarkRecipientDelivered(ctx, notification.NotificationID, ledger.RecipientID, patch.SyncSeq); err != nil {
			failed = true
		}
	}
	if failed {
		return s.retryNotification(ctx, notification, fmt.Errorf("conversation avatar notification has failed recipients"))
	}
	if err := s.store.CompleteNotification(ctx, notification.NotificationID, notification.LeaseToken); err != nil {
		return fmt.Errorf("ack avatar notification: %w", err)
	}
	return nil
}

func (s *ReliableGroupAvatarTaskScheduler) retryNotification(ctx context.Context, notification reliabletask.NotificationOutboxRecord, err error) error {
	return s.store.RetryNotification(ctx, notification.NotificationID, notification.LeaseToken, reliabletask.RuntimeFailure{
		Code:    "CHAT.GROUP_AVATAR.notification_failed",
		Message: err.Error(),
		Attributes: map[string]string{
			"conversationId": notification.AggregateID,
		},
	}, s.retryPolicy, time.Now().UTC())
}

func stringifyPayload(payload map[string]any) map[string]string {
	out := make(map[string]string, len(payload))
	for key, value := range payload {
		out[key] = fmt.Sprint(value)
	}
	return out
}

func anyPayload(payload map[string]string) map[string]any {
	out := make(map[string]any, len(payload))
	for key, value := range payload {
		out[key] = value
	}
	return out
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

func (s *ReliableGroupAvatarTaskScheduler) MetricsSnapshot() map[string]float64 {
	return map[string]float64{}
}

func (s *ReliableGroupAvatarTaskScheduler) PublishAvatarUpdatedEvent(ctx context.Context, conversationID string, actorID string, payload map[string]any) error {
	if s == nil || s.publisher == nil {
		return nil
	}
	return s.publisher.PublishDomainEvent(ctx, event.ConversationAvatarUpdated, conversationID, actorID, payload)
}
