package persistence

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"

	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/domain"
)

type MemoryRepository struct {
	mu    sync.RWMutex
	facts map[string]domain.Fact
}

func NewMemoryRepository() *MemoryRepository {
	return &MemoryRepository{facts: map[string]domain.Fact{}}
}

func (repository *MemoryRepository) AppendIfAbsent(
	_ context.Context,
	fact domain.Fact,
) (bool, error) {
	canonical, err := domain.NewFact(fact)
	if err != nil {
		return false, err
	}
	repository.mu.Lock()
	defer repository.mu.Unlock()
	if existing, found := repository.facts[canonical.DeadLetterID]; found {
		if existing != canonical {
			return false, fmt.Errorf(
				"external interaction dead letter %s conflicts with immutable fact",
				canonical.DeadLetterID,
			)
		}
		return false, nil
	}
	repository.facts[canonical.DeadLetterID] = canonical
	return true, nil
}

func (repository *MemoryRepository) ListByRequest(
	_ context.Context,
	requestID string,
) ([]domain.Fact, error) {
	requestID = strings.TrimSpace(requestID)
	if requestID == "" {
		return nil, fmt.Errorf("requestId is required")
	}
	repository.mu.RLock()
	defer repository.mu.RUnlock()
	facts := make([]domain.Fact, 0)
	for _, fact := range repository.facts {
		if fact.RequestID == requestID {
			facts = append(facts, fact)
		}
	}
	sort.Slice(facts, func(left, right int) bool {
		if facts[left].CreatedAt.Equal(facts[right].CreatedAt) {
			return facts[left].DeadLetterID < facts[right].DeadLetterID
		}
		return facts[left].CreatedAt.Before(facts[right].CreatedAt)
	})
	return facts, nil
}
