package persistence

import (
	"context"
	"sort"
	"sync"
	"time"

	rterr "quwoquan_service/runtime/errors"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

type memorySkillSubscriptionReceipt struct {
	commandKind   string
	commandDigest string
	result        skillmodel.SkillSubscription
}

type MemoryStore struct {
	mu            sync.RWMutex
	subscriptions map[string]skillmodel.SkillSubscription
	receipts      map[string]memorySkillSubscriptionReceipt
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		subscriptions: map[string]skillmodel.SkillSubscription{},
		receipts:      map[string]memorySkillSubscriptionReceipt{},
	}
}

// SeedSkillSubscription establishes preconditions for local contract tests.
// Runtime composition never calls this helper.
func (s *MemoryStore) SeedSkillSubscription(subscription skillmodel.SkillSubscription) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if subscription.Version == 0 {
		subscription.Version = 1
	}
	s.subscriptions[subscription.SubscriptionID] = subscription
}

func (s *MemoryStore) GetSkillSubscriptionCommandResult(
	_ context.Context,
	ownerID string,
	commandID string,
	commandKind string,
	commandDigest string,
) (skillmodel.SkillSubscription, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	receipt, ok := s.receipts[ownerID+"\x00"+commandID]
	if !ok {
		return skillmodel.SkillSubscription{}, false, nil
	}
	if receipt.commandKind != commandKind || receipt.commandDigest != commandDigest {
		return skillmodel.SkillSubscription{}, false, skillmodel.ErrIdempotencyConflict
	}
	return receipt.result, true, nil
}

func (s *MemoryStore) CreateSkillSubscription(
	_ context.Context,
	commandID string,
	commandDigest string,
	subscription skillmodel.SkillSubscription,
) (skillmodel.SkillSubscription, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receiptKey := subscription.Owner.OwnerID + "\x00" + commandID
	if receipt, ok := s.receipts[receiptKey]; ok {
		if receipt.commandKind != "create" || receipt.commandDigest != commandDigest {
			return skillmodel.SkillSubscription{}, false, skillmodel.ErrIdempotencyConflict
		}
		return receipt.result, true, nil
	}
	subscription.Version = 1
	s.subscriptions[subscription.SubscriptionID] = subscription
	s.receipts[receiptKey] = memorySkillSubscriptionReceipt{
		commandKind:   "create",
		commandDigest: commandDigest,
		result:        subscription,
	}
	return subscription, false, nil
}

func (s *MemoryStore) GetSkillSubscription(_ context.Context, userID, subscriptionID string) (skillmodel.SkillSubscription, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok || subscription.Owner.OwnerID != userID {
		return skillmodel.SkillSubscription{}, skillmodel.ErrNotFound
	}
	return subscription, nil
}

func (s *MemoryStore) ListSkillSubscriptions(_ context.Context, userID, status string, limit int) ([]skillmodel.SkillSubscription, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]skillmodel.SkillSubscription, 0, len(s.subscriptions))
	for _, subscription := range s.subscriptions {
		if userID != "" && subscription.Owner.OwnerID != userID {
			continue
		}
		if status != "" && subscription.Status != status {
			continue
		}
		if status == "" && subscription.Status == skillmodel.SkillSubscriptionStatusArchived {
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

func (s *MemoryStore) ListActiveSkillSubscriptionsForDelivery(
	_ context.Context,
	dueAt time.Time,
	limit int,
) ([]skillmodel.SkillSubscription, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]skillmodel.SkillSubscription, 0, len(s.subscriptions))
	for _, subscription := range s.subscriptions {
		next := subscription.DeliveryState.NextAttemptAt
		if subscription.Status == skillmodel.SkillSubscriptionStatusActive &&
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

func (s *MemoryStore) UpdateSkillSubscriptionStatus(
	_ context.Context,
	userID string,
	subscriptionID string,
	status string,
	nextAttemptAt *time.Time,
	updatedAt time.Time,
	commandID string,
	commandDigest string,
) (skillmodel.SkillSubscription, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	receiptKey := userID + "\x00" + commandID
	if receipt, ok := s.receipts[receiptKey]; ok {
		if receipt.commandKind != "update_status" || receipt.commandDigest != commandDigest {
			return skillmodel.SkillSubscription{}, false, skillmodel.ErrIdempotencyConflict
		}
		return receipt.result, true, nil
	}
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok || subscription.Owner.OwnerID != userID {
		return skillmodel.SkillSubscription{}, false, skillmodel.ErrNotFound
	}
	if subscription.Status == status {
		s.receipts[receiptKey] = memorySkillSubscriptionReceipt{commandKind: "update_status", commandDigest: commandDigest, result: subscription}
		return subscription, false, nil
	}
	subscription.Status = status
	if status != skillmodel.SkillSubscriptionStatusActive {
		subscription.DeliveryState.PendingDeliveryID = ""
		subscription.DeliveryState.ConsecutiveFailures = 0
		subscription.DeliveryState.LastErrorCode = ""
		subscription.DeliveryState.NextAttemptAt = nil
	} else if nextAttemptAt != nil {
		next := nextAttemptAt.UTC()
		subscription.DeliveryState.NextAttemptAt = &next
	}
	subscription.UpdatedAt = updatedAt
	subscription.Version++
	s.subscriptions[subscriptionID] = subscription
	s.receipts[receiptKey] = memorySkillSubscriptionReceipt{commandKind: "update_status", commandDigest: commandDigest, result: subscription}
	return subscription, false, nil
}

func (s *MemoryStore) BeginSkillSubscriptionDelivery(
	_ context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	attemptedAt time.Time,
) (skillmodel.SkillSubscription, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok || subscription.Owner.OwnerID != userID {
		return skillmodel.SkillSubscription{}, false, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"订阅不存在",
			"skill subscription not found",
		)
	}
	if subscription.Status != skillmodel.SkillSubscriptionStatusActive {
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
	subscription.Version++
	s.subscriptions[subscriptionID] = subscription
	return subscription, true, nil
}

func (s *MemoryStore) CompleteSkillSubscriptionDelivery(
	_ context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	deliveredAt time.Time,
	nextAttemptAt time.Time,
) (skillmodel.SkillSubscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok ||
		subscription.Owner.OwnerID != userID ||
		subscription.DeliveryState.PendingDeliveryID != deliveryID {
		return skillmodel.SkillSubscription{}, rterr.NewInvalidArgument(
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
	subscription.Version++
	s.subscriptions[subscriptionID] = subscription
	return subscription, nil
}

func (s *MemoryStore) RecordSkillSubscriptionDeliveryFailure(
	_ context.Context,
	userID string,
	subscriptionID string,
	deliveryID string,
	errorCode string,
	failedAt time.Time,
	nextAttemptAt time.Time,
) (skillmodel.SkillSubscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok ||
		subscription.Owner.OwnerID != userID ||
		subscription.DeliveryState.PendingDeliveryID != deliveryID {
		return skillmodel.SkillSubscription{}, rterr.NewInvalidArgument(
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
	subscription.Version++
	s.subscriptions[subscriptionID] = subscription
	return subscription, nil
}

func (s *MemoryStore) ClearPendingSkillSubscriptionDelivery(
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
	subscription.Version++
	s.subscriptions[subscriptionID] = subscription
	return nil
}
