package persistence

import (
	"context"
	"sync"

	"quwoquan_service/services/product-ops-service/internal/application"
)

// MemoryGrowthStore 是 GrowthStore 的 local_contract 实现，语义与 Mongo 一致。
type MemoryGrowthStore struct {
	mu        sync.Mutex
	daily     map[string]application.DailyActivity
	firstSeen map[string]string // actorHash -> firstSeenDate
}

func NewMemoryGrowthStore() *MemoryGrowthStore {
	return &MemoryGrowthStore{
		daily:     map[string]application.DailyActivity{},
		firstSeen: map[string]string{},
	}
}

func (s *MemoryGrowthStore) UpsertDailyActivity(_ context.Context, activity application.DailyActivity) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.daily[activity.Date] = activity
	return nil
}

func (s *MemoryGrowthStore) ListDailyActivity(_ context.Context, fromDate, toDate string) ([]application.DailyActivity, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items := make([]application.DailyActivity, 0, len(s.daily))
	for date, item := range s.daily {
		if date >= fromDate && date <= toDate {
			items = append(items, item)
		}
	}
	return items, nil
}

func (s *MemoryGrowthStore) EnsureActorFirstSeen(_ context.Context, date string, actorHashes []string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, actorHash := range actorHashes {
		if _, exists := s.firstSeen[actorHash]; !exists {
			s.firstSeen[actorHash] = date
		}
	}
	return nil
}

func (s *MemoryGrowthStore) ListActorFirstSeen(_ context.Context, date string) ([]string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	actors := make([]string, 0)
	for actorHash, firstSeenDate := range s.firstSeen {
		if firstSeenDate == date {
			actors = append(actors, actorHash)
		}
	}
	return actors, nil
}

var _ application.GrowthStore = (*MemoryGrowthStore)(nil)
