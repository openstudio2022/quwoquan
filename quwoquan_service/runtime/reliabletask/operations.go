package reliabletask

import (
	"context"
	"strings"
	"sync"
	"time"
)

type DeadTaskRecord struct {
	TaskID      string            `json:"taskId"`
	TaskType    string            `json:"taskType"`
	AggregateID string            `json:"aggregateId"`
	Attempts    int               `json:"attempts"`
	LastFailure *RuntimeFailure   `json:"lastFailure,omitempty"`
	Payload     map[string]string `json:"payload,omitempty"`
	UpdatedAt   time.Time         `json:"updatedAt"`
}

type DeadNotificationRecord struct {
	NotificationID        string          `json:"notificationId"`
	SubjectNotificationID string          `json:"subjectNotificationId"`
	Channel               string          `json:"channel"`
	EventType             string          `json:"eventType"`
	AggregateID           string          `json:"aggregateId"`
	Attempts              int             `json:"attempts"`
	AttemptEpoch          int             `json:"attemptEpoch"`
	LastFailure           *RuntimeFailure `json:"lastFailure,omitempty"`
	UpdatedAt             time.Time       `json:"updatedAt"`
}

type DLQRecoveryStore interface {
	ListDeadTasks(ctx context.Context, taskTypes []string, limit int) ([]DeadTaskRecord, error)
	RecoverDeadTask(ctx context.Context, taskID string, now time.Time) error
	ListDeadNotifications(ctx context.Context, eventTypes []string, limit int) ([]DeadNotificationRecord, error)
	RecoverDeadNotification(ctx context.Context, notificationID string, now time.Time) error
}

// TaskRecoveryReceipt is the durable replay fact for one dead-task recovery
// command. A stable idempotency key may bind to exactly one task.
type TaskRecoveryReceipt struct {
	IdempotencyKey string    `bson:"_id" json:"idempotencyKey"`
	TaskID         string    `bson:"taskId" json:"taskId"`
	RecoveredAt    time.Time `bson:"recoveredAt" json:"recoveredAt"`
	ExpiresAt      time.Time `bson:"expiresAt" json:"expiresAt"`
}

type IdempotentDLQRecoveryStore interface {
	RecoverDeadTaskIdempotently(
		ctx context.Context,
		taskID string,
		idempotencyKey string,
		now time.Time,
	) (TaskRecoveryReceipt, bool, error)
}

type RetentionCleanupStore interface {
	CleanupReliableTaskRetention(ctx context.Context, policy RetentionPolicy, now time.Time) (RetentionCleanupResult, error)
}

type RetentionCleanupResult struct {
	OutboxesDeleted      int64 `json:"outboxesDeleted"`
	TasksDeleted         int64 `json:"tasksDeleted"`
	NotificationsDeleted int64 `json:"notificationsDeleted"`
	LedgersDeleted       int64 `json:"ledgersDeleted"`
	AttemptsDeleted      int64 `json:"attemptsDeleted"`
}

type MetricsStore interface {
	ReliableTaskMetrics(ctx context.Context) (MetricsSnapshot, error)
}

type MetricsSnapshot struct {
	TasksByStatus         map[string]int64 `json:"tasksByStatus"`
	NotificationsByStatus map[string]int64 `json:"notificationsByStatus"`
	ProviderAttempts      map[string]int64 `json:"providerAttempts"`
	DeadTasks             int64            `json:"deadTasks"`
	DeadNotifications     int64            `json:"deadNotifications"`
	UpdatedAt             time.Time        `json:"updatedAt"`
}

type RateLimiter struct {
	mu      sync.Mutex
	buckets map[string]rateBucket
	now     func() time.Time
}

type rateBucket struct {
	windowStart time.Time
	count       int
}

func NewRateLimiter() *RateLimiter {
	return &RateLimiter{
		buckets: map[string]rateBucket{},
		now:     func() time.Time { return time.Now().UTC() },
	}
}

func (l *RateLimiter) Allow(key string, perSecond int) bool {
	if l == nil || perSecond <= 0 {
		return true
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	now := l.now().Truncate(time.Second)
	key = strings.TrimSpace(key)
	if key == "" {
		key = "default"
	}
	bucket := l.buckets[key]
	if bucket.windowStart.IsZero() || !bucket.windowStart.Equal(now) {
		bucket = rateBucket{windowStart: now}
	}
	if bucket.count >= perSecond {
		l.buckets[key] = bucket
		return false
	}
	bucket.count++
	l.buckets[key] = bucket
	return true
}

type RateLimitedWorker struct {
	Worker  Worker
	Limiter *RateLimiter
	Policy  RateLimitPolicy
}

func (w RateLimitedWorker) ProcessOne(ctx context.Context, handler TaskHandler) (bool, error) {
	if w.Limiter != nil && !w.Limiter.Allow("task:"+strings.Join(w.Worker.TaskTypes, ","), w.Policy.ClaimPerSecond) {
		return false, nil
	}
	return w.Worker.ProcessOne(ctx, handler)
}

type RateLimitedNotificationWorker struct {
	Worker  NotificationWorker
	Limiter *RateLimiter
	Policy  RateLimitPolicy
}

func (w RateLimitedNotificationWorker) ProcessOne(ctx context.Context, fanout NotificationFanout) (bool, error) {
	if w.Limiter != nil && !w.Limiter.Allow("notification:"+strings.Join(w.Worker.EventTypes, ","), w.Policy.ClaimPerSecond) {
		return false, nil
	}
	return w.Worker.ProcessOne(ctx, fanout)
}
