package persistence

import (
	"context"
	"sort"
	"sync"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

type MemorySkillSubscriptionStore struct {
	mu            sync.RWMutex
	subscriptions map[string]assistant.SkillSubscription
}

func NewMemorySkillSubscriptionStore() *MemorySkillSubscriptionStore {
	return &MemorySkillSubscriptionStore{subscriptions: map[string]assistant.SkillSubscription{}}
}

func (s *MemorySkillSubscriptionStore) CreateSkillSubscription(_ context.Context, subscription assistant.SkillSubscription) (assistant.SkillSubscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if subscription.ClientRequestID != "" {
		for _, existing := range s.subscriptions {
			if existing.Owner.OwnerID == subscription.Owner.OwnerID &&
				existing.ClientRequestID == subscription.ClientRequestID {
				return existing, nil
			}
		}
	}
	s.subscriptions[subscription.SubscriptionID] = subscription
	return subscription, nil
}

func (s *MemorySkillSubscriptionStore) UpsertSkillSubscription(_ context.Context, subscription assistant.SkillSubscription) (assistant.SkillSubscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if existing, ok := s.subscriptions[subscription.SubscriptionID]; ok {
		subscription.CreatedAt = existing.CreatedAt
	}
	s.subscriptions[subscription.SubscriptionID] = subscription
	return subscription, nil
}

func (s *MemorySkillSubscriptionStore) GetSkillSubscription(_ context.Context, userID, subscriptionID string) (assistant.SkillSubscription, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok || subscription.Owner.OwnerID != userID {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "订阅不存在", "skill subscription not found")
	}
	return subscription, nil
}

func (s *MemorySkillSubscriptionStore) ListSkillSubscriptions(_ context.Context, userID, status string, limit int) ([]assistant.SkillSubscription, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]assistant.SkillSubscription, 0, len(s.subscriptions))
	for _, subscription := range s.subscriptions {
		if userID != "" && subscription.Owner.OwnerID != userID {
			continue
		}
		if status != "" && subscription.Status != status {
			continue
		}
		if status == "" && subscription.Status == assistant.SkillSubscriptionStatusArchived {
			continue
		}
		items = append(items, subscription)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].UpdatedAt.After(items[j].UpdatedAt)
	})
	if limit > 0 && len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}

func (s *MemorySkillSubscriptionStore) ListActiveSkillSubscriptionsForDelivery(
	_ context.Context,
	dueAt time.Time,
	limit int,
) ([]assistant.SkillSubscription, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]assistant.SkillSubscription, 0, len(s.subscriptions))
	for _, subscription := range s.subscriptions {
		next := subscription.DeliveryState.NextAttemptAt
		if subscription.Status == assistant.SkillSubscriptionStatusActive &&
			(next == nil || !next.After(dueAt)) {
			items = append(items, subscription)
		}
	}
	sort.Slice(items, func(i, j int) bool {
		left := items[i].DeliveryState.NextAttemptAt
		right := items[j].DeliveryState.NextAttemptAt
		if left == nil || right == nil {
			if left == nil && right == nil {
				return items[i].UpdatedAt.Before(items[j].UpdatedAt)
			}
			return left == nil
		}
		if left.Equal(*right) {
			return items[i].SubscriptionID < items[j].SubscriptionID
		}
		return left.Before(*right)
	})
	if limit <= 0 || limit > 1000 {
		limit = 1000
	}
	if len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}

func (s *MemorySkillSubscriptionStore) UpdateSkillSubscriptionStatus(
	_ context.Context,
	userID string,
	subscriptionID string,
	status string,
	nextAttemptAt *time.Time,
	updatedAt time.Time,
) (assistant.SkillSubscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok || subscription.Owner.OwnerID != userID {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "订阅不存在", "skill subscription not found")
	}
	if subscription.Status == status {
		// 与 Mongo 实现同语义：目标状态已满足时 no-op 返回存量。
		return subscription, nil
	}
	subscription.Status = status
	if status != assistant.SkillSubscriptionStatusActive {
		subscription.DeliveryState.PendingDeliveryID = ""
		subscription.DeliveryState.ConsecutiveFailures = 0
		subscription.DeliveryState.LastErrorCode = ""
		subscription.DeliveryState.NextAttemptAt = nil
	} else if nextAttemptAt != nil {
		next := nextAttemptAt.UTC()
		subscription.DeliveryState.NextAttemptAt = &next
	}
	subscription.UpdatedAt = updatedAt
	s.subscriptions[subscriptionID] = subscription
	return subscription, nil
}

func (s *MemorySkillSubscriptionStore) BeginSkillSubscriptionDelivery(
	_ context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	attemptedAt time.Time,
) (assistant.SkillSubscription, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok || subscription.Owner.OwnerID != userID {
		return assistant.SkillSubscription{}, false, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"订阅不存在",
			"skill subscription not found",
		)
	}
	if subscription.Status != assistant.SkillSubscriptionStatusActive {
		return subscription, false, nil
	}
	pending := subscription.DeliveryState.PendingDeliveryID
	if pending != "" && pending != deliveryID {
		return subscription, false, nil
	}
	attemptedAt = attemptedAt.UTC()
	subscription.DeliveryState.PendingDeliveryID = deliveryID
	subscription.DeliveryState.LastAttemptAt = &attemptedAt
	subscription.UpdatedAt = attemptedAt
	s.subscriptions[subscriptionID] = subscription
	return subscription, true, nil
}

func (s *MemorySkillSubscriptionStore) CompleteSkillSubscriptionDelivery(
	_ context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	deliveredAt time.Time,
	nextAttemptAt time.Time,
) (assistant.SkillSubscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok ||
		subscription.Owner.OwnerID != userID ||
		subscription.DeliveryState.PendingDeliveryID != deliveryID {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"订阅投递状态已变化",
			"skill subscription delivery state changed",
		)
	}
	deliveredAt = deliveredAt.UTC()
	subscription.DeliveryState.PendingDeliveryID = ""
	subscription.DeliveryState.LastAttemptAt = &deliveredAt
	subscription.DeliveryState.LastDeliveredAt = &deliveredAt
	nextAttemptAt = nextAttemptAt.UTC()
	subscription.DeliveryState.NextAttemptAt = &nextAttemptAt
	subscription.DeliveryState.ConsecutiveFailures = 0
	subscription.DeliveryState.LastErrorCode = ""
	subscription.UpdatedAt = deliveredAt
	s.subscriptions[subscriptionID] = subscription
	return subscription, nil
}

func (s *MemorySkillSubscriptionStore) RecordSkillSubscriptionDeliveryFailure(
	_ context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	errorCode string,
	failedAt time.Time,
	nextAttemptAt time.Time,
) (assistant.SkillSubscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok ||
		subscription.Owner.OwnerID != userID ||
		subscription.DeliveryState.PendingDeliveryID != deliveryID {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"订阅投递状态已变化",
			"skill subscription delivery state changed",
		)
	}
	failedAt = failedAt.UTC()
	subscription.DeliveryState.LastAttemptAt = &failedAt
	nextAttemptAt = nextAttemptAt.UTC()
	subscription.DeliveryState.NextAttemptAt = &nextAttemptAt
	subscription.DeliveryState.ConsecutiveFailures++
	subscription.DeliveryState.LastErrorCode = errorCode
	subscription.UpdatedAt = failedAt
	s.subscriptions[subscriptionID] = subscription
	return subscription, nil
}

func (s *MemorySkillSubscriptionStore) ClearPendingSkillSubscriptionDelivery(
	_ context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	clearedAt time.Time,
	nextAttemptAt time.Time,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok || subscription.Owner.OwnerID != userID {
		return rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"订阅不存在",
			"skill subscription not found",
		)
	}
	if subscription.DeliveryState.PendingDeliveryID != deliveryID {
		return nil
	}
	subscription.DeliveryState.PendingDeliveryID = ""
	subscription.DeliveryState.ConsecutiveFailures = 0
	subscription.DeliveryState.LastErrorCode = ""
	nextAttemptAt = nextAttemptAt.UTC()
	subscription.DeliveryState.NextAttemptAt = &nextAttemptAt
	subscription.UpdatedAt = clearedAt.UTC()
	s.subscriptions[subscriptionID] = subscription
	return nil
}
