package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/notification-service/internal/application"
)

type contractDeliveryAdapter struct{}

func (contractDeliveryAdapter) Deliver(
	context.Context,
	reliabletask.NotificationOutboxRecord,
	string,
) (int64, error) {
	return 1, nil
}

func TestNotificationDeliveryConstructorRequiresExplicitDependencies(t *testing.T) {
	policy := reliabletask.RateLimitPolicy{
		ClaimPerSecond:    100,
		DispatchPerSecond: 100,
		RetryPerSecond:    20,
	}
	if _, err := application.NewNotificationDeliveryService(
		nil,
		contractDeliveryAdapter{},
		policy,
	); err == nil {
		t.Fatal("nil store must be rejected")
	}
	var typedNilStore *reliabletask.MemoryStore
	if _, err := application.NewNotificationDeliveryService(
		typedNilStore,
		contractDeliveryAdapter{},
		policy,
	); err == nil {
		t.Fatal("typed nil store must be rejected")
	}
	store := reliabletask.NewMemoryStore()
	if _, err := application.NewNotificationDeliveryService(store, nil, policy); err == nil {
		t.Fatal("nil delivery adapter must be rejected")
	}
	service, err := application.NewNotificationDeliveryService(
		store,
		contractDeliveryAdapter{},
		policy,
	)
	if err != nil {
		t.Fatalf("explicit test dependencies must be accepted: %v", err)
	}
	if service == nil {
		t.Fatal("constructor returned nil service")
	}
}

func TestNotificationDeliveryConstructorRejectsIncompleteRatePolicy(t *testing.T) {
	_, err := application.NewNotificationDeliveryService(
		reliabletask.NewMemoryStore(),
		contractDeliveryAdapter{},
		reliabletask.RateLimitPolicy{ClaimPerSecond: 1},
	)
	if err == nil {
		t.Fatal("incomplete rate policy must be rejected")
	}
}
