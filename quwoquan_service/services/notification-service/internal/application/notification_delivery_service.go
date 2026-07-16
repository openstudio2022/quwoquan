package application

import (
	"context"
	"fmt"
	"reflect"
	"time"

	"quwoquan_service/runtime/reliabletask"
)

const NotificationPushRequestedEvent = "notification.push.requested"

type DeliveryAdapter interface {
	Deliver(ctx context.Context, notification reliabletask.NotificationOutboxRecord, recipientID string) (int64, error)
}

type NotificationDeliveryStore interface {
	reliabletask.Store
}

type NotificationDeliveryService struct {
	worker  reliabletask.NotificationWorker
	adapter DeliveryAdapter
	limiter *reliabletask.RateLimiter
	policy  reliabletask.RateLimitPolicy
}

func NewNotificationDeliveryService(
	store NotificationDeliveryStore,
	adapter DeliveryAdapter,
	policy reliabletask.RateLimitPolicy,
) (*NotificationDeliveryService, error) {
	if isNilDependency(store) {
		return nil, fmt.Errorf("notification delivery store is required")
	}
	if isNilDependency(adapter) {
		return nil, fmt.Errorf("notification delivery adapter is required")
	}
	if policy.DispatchPerSecond <= 0 ||
		policy.ClaimPerSecond <= 0 ||
		policy.RetryPerSecond <= 0 {
		return nil, fmt.Errorf("notification delivery rate limits must be positive")
	}
	return &NotificationDeliveryService{
		worker: reliabletask.NotificationWorker{
			Store:      store,
			EventTypes: []string{NotificationPushRequestedEvent},
			WorkerID:   "notification-delivery-worker",
			LeaseTTL:   30 * time.Second,
			Retry:      reliabletask.DefaultRetryPolicy(),
		},
		adapter: adapter,
		limiter: reliabletask.NewRateLimiter(),
		policy:  policy,
	}, nil
}

func (s *NotificationDeliveryService) ProcessOne(ctx context.Context) (bool, error) {
	worker := reliabletask.RateLimitedNotificationWorker{
		Worker:  s.worker,
		Limiter: s.limiter,
		Policy:  s.policy,
	}
	return worker.ProcessOne(ctx, s.adapter.Deliver)
}

func isNilDependency(value any) bool {
	if value == nil {
		return true
	}
	reflected := reflect.ValueOf(value)
	switch reflected.Kind() {
	case reflect.Chan,
		reflect.Func,
		reflect.Interface,
		reflect.Map,
		reflect.Pointer,
		reflect.Slice:
		return reflected.IsNil()
	default:
		return false
	}
}
