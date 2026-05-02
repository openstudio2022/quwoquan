package persistence

import (
	"context"
	"sort"
	"sync"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
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

func (s *MemorySkillSubscriptionStore) UpdateSkillSubscriptionStatus(_ context.Context, userID, subscriptionID, status string, updatedAt time.Time) (assistant.SkillSubscription, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	subscription, ok := s.subscriptions[subscriptionID]
	if !ok || subscription.Owner.OwnerID != userID {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "订阅不存在", "skill subscription not found")
	}
	subscription.Status = status
	subscription.UpdatedAt = updatedAt
	s.subscriptions[subscriptionID] = subscription
	return subscription, nil
}
