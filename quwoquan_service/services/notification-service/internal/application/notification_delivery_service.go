package application

import (
	"context"
	"time"

	"quwoquan_service/runtime/reliabletask"
)

type DeliveryAdapter interface {
	Deliver(ctx context.Context, notification reliabletask.NotificationOutboxRecord, recipientID string) (int64, error)
}

type NotificationDeliveryService struct {
	store   reliabletask.Store
	worker  reliabletask.NotificationWorker
	adapter DeliveryAdapter
	limiter *reliabletask.RateLimiter
	policy  reliabletask.RateLimitPolicy
}

func NewNotificationDeliveryService(store reliabletask.Store, adapter DeliveryAdapter, policy reliabletask.RateLimitPolicy) *NotificationDeliveryService {
	if store == nil {
		store = reliabletask.NewMemoryStore()
	}
	if adapter == nil {
		adapter = NoopDeliveryAdapter{}
	}
	return &NotificationDeliveryService{
		store: store,
		worker: reliabletask.NotificationWorker{
			Store:      store,
			EventTypes: []string{"notification.push.requested", "notification.in_app.requested"},
			WorkerID:   "notification-delivery-worker",
			LeaseTTL:   30 * time.Second,
			Retry:      reliabletask.DefaultRetryPolicy(),
		},
		adapter: adapter,
		limiter: reliabletask.NewRateLimiter(),
		policy:  policy,
	}
}

func (s *NotificationDeliveryService) ProcessOne(ctx context.Context) (bool, error) {
	worker := reliabletask.RateLimitedNotificationWorker{
		Worker:  s.worker,
		Limiter: s.limiter,
		Policy:  s.policy,
	}
	return worker.ProcessOne(ctx, s.adapter.Deliver)
}

func (s *NotificationDeliveryService) Metrics(ctx context.Context) (reliabletask.MetricsSnapshot, error) {
	metrics, ok := s.store.(reliabletask.MetricsStore)
	if !ok {
		return reliabletask.MetricsSnapshot{}, nil
	}
	return metrics.ReliableTaskMetrics(ctx)
}

func (s *NotificationDeliveryService) RecoverNotification(ctx context.Context, notificationID string) error {
	recovery, ok := s.store.(reliabletask.DLQRecoveryStore)
	if !ok {
		return nil
	}
	return recovery.RecoverDeadNotification(ctx, notificationID, time.Now().UTC())
}

type NoopDeliveryAdapter struct{}

func (NoopDeliveryAdapter) Deliver(ctx context.Context, notification reliabletask.NotificationOutboxRecord, recipientID string) (int64, error) {
	_ = ctx
	_ = notification
	_ = recipientID
	return time.Now().UTC().UnixNano(), nil
}
